"""
websocket functions
"""

from __future__ import annotations

import platform
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, Callable, Generator, Literal, cast
from uuid import uuid4

from opsicommon.client.opsiservice import MessagebusListener
from opsicommon.logging import get_logger  # type: ignore[import]
from opsicommon.messagebus import (
	CONNECTION_USER_CHANNEL,
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	JSONRPCRequestMessage,
	JSONRPCResponseMessage,
	Message,
	ProcessDataReadMessage,
	ProcessErrorMessage,
	ProcessStartEventMessage,
	ProcessStartRequestMessage,
	ProcessStopEventMessage,
	ProcessStopRequestMessage,
	TerminalCloseEventMessage,
	TerminalDataReadMessage,
	TerminalDataWriteMessage,
	TerminalErrorMessage,
	TerminalOpenEventMessage,
	TerminalOpenRequestMessage,
)
from opsicommon.system.info import is_windows

from opsicli.io import get_console
from opsicli.opsiservice import get_service_connection
from opsicli.utils import stream_wrap

if platform.system().lower() == "windows":
	import msvcrt

CHANNEL_SUB_TIMEOUT = 5.0
JSONRPC_TIMEOUT = 15.0
PROCESS_START_TIMEOUT = 10.0

logger = get_logger("opsicli")


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	debug_string = ""
	for key, value in message.to_dict().items():
		debug_string += f"\t{key}: {value}\n"
	logger.debug(debug_string)
	# logger.devel(debug_string)  # for test_messagebus.py


class MessagebusConnection(MessagebusListener):
	def __init__(self) -> None:
		MessagebusListener.__init__(self)
		self.channel_subscription_locks: dict[str, Event] = {}
		self.subscribed_channels: list[str] = []
		self.initial_subscription_event = Event()
		self.service_client = get_service_connection()

	def message_received(self, message: Message) -> None:
		log_message(message)
		try:
			callback_name = f"_on_{message.type}"
			if hasattr(self, callback_name):
				callback = getattr(self, callback_name)
				callback(message)
			else:
				logger.debug("No available callback for event of message %r", message.type)
		except Exception as err:
			logger.error(err, exc_info=True)

	def _on_channel_subscription_event(self, message: ChannelSubscriptionEventMessage) -> None:
		self.subscribed_channels = message.subscribed_channels
		for channel in message.subscribed_channels:
			if channel in self.channel_subscription_locks:
				self.channel_subscription_locks[channel].set()
			else:
				self.initial_subscription_event.set()

	def subscribe_to_channel(self, channel: str) -> None:
		if channel in self.subscribed_channels:
			return
		try:
			self.channel_subscription_locks[channel] = Event()
			csr = ChannelSubscriptionRequestMessage(
				sender=CONNECTION_USER_CHANNEL, operation="add", channels=[channel], channel="service:messagebus"
			)
			logger.notice("Requesting access to channel %r", channel)
			log_message(csr)
			self.service_client.messagebus.send_message(csr)
			if not self.channel_subscription_locks[channel].wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError(f"Could not subscribe to channel {channel}")
		finally:
			del self.channel_subscription_locks[channel]

	@contextmanager
	def connection(self) -> Generator[MessagebusConnection, None, None]:
		try:
			if not self.service_client.messagebus_connected:
				logger.debug("Connecting to messagebus.")
				self.service_client.connect_messagebus()
			with self.register(self.service_client.messagebus):
				if not self.initial_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel.")
				yield self
		finally:
			if self.service_client.messagebus_connected:
				logger.debug("Disconnecting from messagebus.")
				self.service_client.disconnect_messagebus()


class JSONRPCMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.jsonrpc_response_events: dict[str | int, Event] = {}
		self.jsonrpc_responses: dict[str | int, Any] = {}

	def _on_jsonrpc_response(self, message: JSONRPCResponseMessage) -> None:
		logger.notice("Received jsonrpc response message")
		self.jsonrpc_responses[message.rpc_id] = message.error if message.error else message.result
		self.jsonrpc_response_events[message.rpc_id].set()

	def jsonrpc(self, channels: list[str], method: str, params: tuple | None = None, timeout: float = JSONRPC_TIMEOUT) -> dict[str, Any]:
		results: dict[str, Any] = {}
		rpc_ids: dict[str, str | int] = {}
		for channel in channels:
			message = JSONRPCRequestMessage(
				method=method,
				params=params or (),
				api_version="2.0",
				sender=CONNECTION_USER_CHANNEL,
				channel=channel,
			)
			self.jsonrpc_response_events[message.rpc_id] = Event()
			rpc_ids[channel] = message.rpc_id
			self.service_client.messagebus.send_message(message)
		logger.notice("Sent jsonrpc-request, awaiting response...")
		for channel, rpc_id in rpc_ids.items():
			if not self.jsonrpc_response_events[rpc_id].wait(timeout):
				results[channel] = TimeoutError("Timed out waiting for jsonrpc response.")
			elif not self.jsonrpc_responses[rpc_id]:
				results[channel] = ConnectionError("Failed to receive jsonrpc response.")
			else:
				results[channel] = self.jsonrpc_responses[rpc_id]
			if rpc_id in self.jsonrpc_responses:
				del self.jsonrpc_responses[rpc_id]
			if rpc_id in self.jsonrpc_response_events:
				del self.jsonrpc_response_events[rpc_id]
		return results


@dataclass
class MessagebusProcess:
	process_id: str
	write_function: Callable
	start_request: ProcessStartRequestMessage
	start_request_time: float = 0.0
	start_event: ProcessStartEventMessage | None = None
	start_event_time: float = 0.0
	stop_event: ProcessStopEventMessage | None = None
	stop_time: float = 0.0
	error: ProcessErrorMessage | str | None = None
	stderr_buffer: bytearray = field(default_factory=bytearray)
	stdout_buffer: bytearray = field(default_factory=bytearray)
	max_buffer_size: int = 100_000
	process_lock: Lock = field(default_factory=Lock)

	@property
	def locale_encoding(self) -> str | None:
		if self.start_event and self.start_event.locale_encoding:
			return self.start_event.locale_encoding
		return None

	@property
	def host_name(self) -> str | None:
		if self.start_request:
			return self.start_request.channel.removeprefix("host:")
		return None

	def on_start_event(self, start_event: ProcessStartEventMessage) -> None:
		with self.process_lock:
			self.start_event = start_event
			self.start_event_time = time.time()

	def on_stop_event(self, stop_event: ProcessStopEventMessage) -> None:
		with self.process_lock:
			self.stop_event = stop_event
			self.stop_time = time.time()
			self._write_all_out()

	def on_error(self, error: ProcessErrorMessage | str) -> None:
		with self.process_lock:
			if self.error:
				# Only the first error is relevant, subsequent errors are ignored
				return
			self.error = error
			self.stop_time = time.time()
			self._write_all_out()
			error_str = str(error.error.message) if isinstance(error, ProcessErrorMessage) else error
			self.write_function(
				data=(error_str + "\n").encode(self.locale_encoding or "utf-8"),
				stream="stderr",
				data_encoding=self.locale_encoding,
				host_name=self.host_name,
				is_error=True,
			)

	def on_data_read(self, message: ProcessDataReadMessage) -> None:
		with self.process_lock:
			for buffer, data, stream in (
				(self.stdout_buffer, message.stdout, "stdout"),
				(self.stderr_buffer, message.stderr, "stderr"),
			):
				buffer.extend(data)
				idx = buffer.rfind(b"\n")
				if idx == -1 and len(buffer) > self.max_buffer_size:
					idx = self.max_buffer_size
				if idx != -1:
					self.write_function(
						data=buffer[: idx + 1],
						stream=cast(Literal["stdout", "stderr"], stream),
						data_encoding=self.locale_encoding,
						host_name=self.host_name,
					)
					if buffer == self.stdout_buffer:
						self.stdout_buffer = buffer[idx + 1 :]
					else:
						self.stderr_buffer = buffer[idx + 1 :]

	def _write_all_out(self) -> None:
		for buffer in self.stdout_buffer, self.stderr_buffer:
			if len(buffer):
				self.write_function(
					data=buffer,
					stream="stdout" if buffer == self.stdout_buffer else "stderr",
					data_encoding=self.locale_encoding,
					host_name=self.host_name,
				)
				if buffer == self.stdout_buffer:
					self.stdout_buffer = bytearray()
				else:
					self.stderr_buffer = bytearray()


class ProcessMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		self.console = get_console()
		self.out_lock = Lock()
		self.show_host_names = False
		self.max_host_name_length = 0
		self.data_encoding = "auto"
		self.output_encoding = "cp437" if is_windows() else "utf-8"
		self.processes: dict[str, MessagebusProcess] = {}
		MessagebusConnection.__init__(self)

	def _on_process_data_read(self, message: ProcessDataReadMessage) -> None:
		logger.debug("Received process data read message")
		self.processes[message.process_id].on_data_read(message)

	def _on_process_stop_event(self, message: ProcessStopEventMessage) -> None:
		logger.debug("Received process stop event message")
		self.processes[message.process_id].on_stop_event(message)

	def _on_process_start_event(self, message: ProcessStartEventMessage) -> None:
		logger.debug("Received process start event message")
		self.processes[message.process_id].on_start_event(message)

	def _on_process_error(self, message: ProcessErrorMessage) -> None:
		logger.debug("Received process error message")
		self.processes[message.process_id].on_error(message)

	def get_host_name(self, process_id: str, padded: bool = False) -> str | None:
		if process := self.processes.get(process_id):
			host_name = process.host_name
			if host_name and padded:
				host_name = host_name.ljust(self.max_host_name_length)
			return host_name
		return None

	def write_out(
		self,
		*,
		data: bytes,
		stream: Literal["stdout", "stderr"],
		data_encoding: str | None,
		host_name: str | None = None,
		is_error: bool = False,
	) -> None:
		if not data:
			return

		use_encoding = None
		if self.data_encoding == "raw":
			use_encoding = None
		elif self.data_encoding == "auto":
			use_encoding = data_encoding or "utf-8"
		else:
			use_encoding = self.data_encoding

		raw_output = use_encoding in (None, self.output_encoding)
		write = sys.stdout.buffer.write if stream == "stdout" else sys.stderr.buffer.write
		flush = sys.stdout.flush if stream == "stdout" else sys.stderr.flush

		with self.out_lock:
			if self.show_host_names and host_name:
				host_name = host_name.ljust(self.max_host_name_length)
				line_prefix = f"{host_name}: ".encode(use_encoding or self.output_encoding)
				data = b"\n".join(line_prefix + line if line else line for line in data.split(b"\n"))

			if is_error and use_encoding:
				self.console.print(f"[red]{data.decode(use_encoding)}[/red]", end="")
				return
			if not raw_output and use_encoding:
				data = data.decode(use_encoding).encode(self.output_encoding)
			write(data)
			flush()

	def execute_processes(
		self,
		*,
		channels: list[str],
		command: tuple[str],
		shell: bool = False,
		concurrent: int = 100,
		show_host_names: bool = True,
		timeout: int = 0,
		encoding: str = "auto",
	) -> int:
		self.show_host_names = show_host_names
		self.data_encoding = encoding
		start_timeout = min(PROCESS_START_TIMEOUT, timeout)
		self.processes = {}

		uniq_channels = list(set(channels))
		if len(uniq_channels) != len(channels):
			raise RuntimeError("Duplicate channels in list of channels.")

		for channel in channels:
			message = ProcessStartRequestMessage(
				command=command,
				sender=CONNECTION_USER_CHANNEL,
				channel=channel,
				shell=shell,
			)
			self.processes[message.process_id] = MessagebusProcess(
				process_id=message.process_id, write_function=self.write_out, start_request=message
			)
			self.max_host_name_length = max(self.max_host_name_length, len(self.get_host_name(message.process_id) or ""))

		while True:
			num_running_processes = 0
			waiting_processes: list[MessagebusProcess] = []
			for process in self.processes.values():
				if process.stop_time:
					# Process completed or failed
					continue

				if process.start_event_time:
					# Start event received, but no stop event yet
					wait_time = time.time() - process.start_event_time
					if timeout <= 0 or wait_time < timeout:
						num_running_processes += 1
						continue

					logger.warning(
						"Timeout reached after %0.2f seconds while waiting for process to end on %r",
						wait_time,
						process.host_name,
					)
					process.on_error("Process timeout")
					self.service_client.messagebus.send_message(
						ProcessStopRequestMessage(
							process_id=process.process_id,
							sender=CONNECTION_USER_CHANNEL,
							channel=process.start_request.channel,
						)
					)
					continue

				if process.start_request_time:
					# Start request was sent, but no start event received yet
					wait_time = time.time() - process.start_request_time
					if wait_time < start_timeout:
						num_running_processes += 1
						continue

					logger.warning(
						"Timeout reached after %0.2f seconds while waiting for process to start on %r",
						wait_time,
						process.host_name,
					)
					process.on_error("Failed to start process")

				elif not process.start_request_time:
					# Start request not sent yet
					waiting_processes.append(process)

			if not num_running_processes and not waiting_processes:
				break

			start_new_processes = min(len(waiting_processes), max(0, concurrent - num_running_processes))
			for idx in range(start_new_processes):
				if waiting_processes[idx].start_request_time:
					raise RuntimeError("Start request already sent")
				logger.debug("Sending process start request")
				waiting_processes[idx].start_request_time = time.time()
				self.service_client.messagebus.send_message(waiting_processes[idx].start_request)

			time.sleep(0.5)

		exit_code = 0
		errors = []
		for process in self.processes.values():
			if exit_code == 0 and process.stop_event and process.stop_event.exit_code != 0:
				exit_code = process.stop_event.exit_code
			if process.error:
				errors.append(process.error)
		if exit_code == 0 and errors:
			exit_code = 1
		return exit_code


class TerminalMessagebusConnection(MessagebusConnection):
	terminal_id: str

	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.should_close = False
		self.terminal_write_channel: str | None = None
		self.terminal_open_event = Event()

	def _on_terminal_open_event(self, message: TerminalOpenEventMessage) -> None:
		if message.terminal_id == self.terminal_id:
			self.terminal_write_channel = message.back_channel
			self.terminal_open_event.set()

	def _on_terminal_data_read(self, message: TerminalDataReadMessage) -> None:
		if message.terminal_id == self.terminal_id:
			sys.stdout.buffer.write(message.data)
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')

	def _on_terminal_error(self, message: TerminalErrorMessage) -> None:
		if message.terminal_id == self.terminal_id:
			logger.notice("received terminal error event - shutting down")
			sys.stdout.buffer.write(b"\nreceived terminal error event - press Enter to return to local shell")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
			self.should_close = True

	def _on_terminal_close_event(self, message: TerminalCloseEventMessage) -> None:
		if message.terminal_id == self.terminal_id:
			logger.notice("received terminal close event - shutting down")
			sys.stdout.buffer.write(b"\nreceived terminal close event - press Enter to return to local shell")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
			self.should_close = True

	def transmit_input(self, term_write_channel: str, data: bytes | None = None) -> None:
		if not self.terminal_id:
			raise ValueError("Terminal id not set.")
		if data:
			tdw = TerminalDataWriteMessage(
				sender=CONNECTION_USER_CHANNEL, channel=term_write_channel, terminal_id=self.terminal_id, data=data
			)
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)
			return
		# If no data is given, transmit from stdin until EOF
		while not self.should_close:
			if platform.system().lower() == "windows":
				data = msvcrt.getch()  # type: ignore
			else:
				data = sys.stdin.read(1).encode("utf-8")
			if not data:  # or data == b"\x03":  # Ctrl+C
				self.should_close = True
				break
			if not self.should_close:
				self.transmit_input(term_write_channel, data)

	def open_new_terminal(self, term_request_channel: str) -> None:
		self.subscribe_to_channel(f"session:{self.terminal_id}")
		size = shutil.get_terminal_size()
		tor = TerminalOpenRequestMessage(
			sender=CONNECTION_USER_CHANNEL,
			channel=term_request_channel,
			terminal_id=self.terminal_id,
			back_channel=f"session:{self.terminal_id}",
			rows=size.lines,
			cols=size.columns,
		)
		logger.notice("Requesting to open terminal with id %s ", self.terminal_id)
		log_message(tor)
		self.service_client.messagebus.send_message(tor)

	def get_terminal_channel_pair(self, target: str) -> tuple[str, str]:
		term_read_channel = f"session:{self.terminal_id}"
		self.subscribe_to_channel(term_read_channel)

		if target.lower() == "configserver":
			term_request_channel = "service:config:terminal"
		else:
			term_request_channel = f"host:{target}"

		self.open_new_terminal(term_request_channel)
		if not self.terminal_open_event.wait(CHANNEL_SUB_TIMEOUT) or self.terminal_write_channel is None:
			raise ConnectionError("Could not open new terminal")
		self.terminal_open_event.clear()  # prepare for catching the next terminal_open_event

		return (term_read_channel, self.terminal_write_channel)

	def run_terminal(self, target: str, term_id: str | None = None) -> None:
		if term_id:
			self.terminal_id = term_id
		else:
			self.terminal_id = str(uuid4())
		with self.connection():
			(_, term_write_channel) = self.get_terminal_channel_pair(target)
			logger.notice("Return to local shell with 'exit' or 'Ctrl+D'")
			with stream_wrap():
				self.transmit_input(term_write_channel)
