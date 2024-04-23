"""
websocket functions
"""

from __future__ import annotations

import os
import selectors
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Event, Lock
from types import FrameType
from typing import Any, Callable, Generator, Literal, cast
from uuid import uuid4

from opsicommon.client.opsiservice import MessagebusListener
from opsicommon.logging import get_logger
from opsicommon.messagebus import CONNECTION_USER_CHANNEL
from opsicommon.messagebus.message import (
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	GeneralErrorMessage,
	JSONRPCRequestMessage,
	JSONRPCResponseMessage,
	Message,
	ProcessDataReadMessage,
	ProcessDataWriteMessage,
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
	TerminalResizeRequestMessage,
)
from opsicommon.system.info import is_windows
from opsicommon.types import forceHostId
from rich.color import ANSI_COLOR_NAMES, Color

from opsicli.io import get_console, read_input_raw_bin
from opsicli.opsiservice import get_service_connection
from opsicli.utils import raw_terminal

if is_windows():
	import win32console  # type: ignore[import-not-found]
else:
	import fcntl
	from signal import SIGWINCH, signal

CHANNEL_SUB_TIMEOUT = 15.0
JSONRPC_TIMEOUT = 15.0
PROCESS_START_TIMEOUT = 15.0

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
		self.channel_subscription_events: dict[str, Event] = {}
		self.subscribed_channels: list[str] = []
		self.initial_subscription_event = Event()
		self.service_client = get_service_connection()

	def send_message(self, message: Message) -> None:
		log_message(message)
		self.service_client.messagebus.send_message(message)

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
		if not self.initial_subscription_event.is_set():
			self.initial_subscription_event.set()
		for channel in message.subscribed_channels:
			if channel in self.channel_subscription_events:
				self.channel_subscription_events[channel].set()

	def subscribe_to_channel(self, channel: str) -> None:
		if channel in self.subscribed_channels:
			return
		try:
			self.channel_subscription_events[channel] = Event()
			message = ChannelSubscriptionRequestMessage(
				sender=CONNECTION_USER_CHANNEL, operation="add", channels=[channel], channel="service:messagebus"
			)
			logger.notice("Requesting access to channel %r", channel)
			self.send_message(message)
			if not self.channel_subscription_events[channel].wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError(f"Could not subscribe to channel {channel}")
		finally:
			del self.channel_subscription_events[channel]

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
			self.send_message(message)
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
	send_message: Callable
	start_request: ProcessStartRequestMessage
	start_request_time: float = 0.0
	start_event: ProcessStartEventMessage | None = None
	start_event_time: float = 0.0
	stop_event: ProcessStopEventMessage | None = None
	stop_time: float = 0.0
	error: ProcessErrorMessage | str | None = None
	prefix_color: Color | None = None
	last_data_created = 0
	stderr_buffer: bytearray = field(default_factory=bytearray)
	stdout_buffer: bytearray = field(default_factory=bytearray)
	stdin_data: bytearray = field(default_factory=bytearray)
	max_buffer_size: int = 100_000
	process_lock: Lock = field(default_factory=Lock)

	@property
	def locale_encoding(self) -> str:
		if self.start_event and self.start_event.locale_encoding:
			return self.start_event.locale_encoding
		return "utf-8"

	@property
	def host_name(self) -> str | None:
		if self.start_request:
			return self.start_request.channel.removeprefix("host:")
		return None

	def on_start_event(self, start_event: ProcessStartEventMessage) -> None:
		with self.process_lock:
			self.start_event = start_event
			self.start_event_time = time.time()
			if not self.stdin_data:
				return

			pos = 0
			chunk_size = 32768
			while pos < len(self.stdin_data):
				self.send_message(
					ProcessDataWriteMessage(
						process_id=self.process_id,
						sender=CONNECTION_USER_CHANNEL,
						channel=self.start_request.channel,
						stdin=self.stdin_data[pos : pos + chunk_size],
					)
				)
				pos += chunk_size
			self.send_message(
				ProcessDataWriteMessage(
					process_id=self.process_id,
					sender=CONNECTION_USER_CHANNEL,
					channel=self.start_request.channel,
					stdin=b"",
				)
			)

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
				data=(error_str + "\n").encode(self.locale_encoding),
				stream="stderr",
				data_encoding=self.locale_encoding,
				host_name=self.host_name,
				prefix_color=self.prefix_color,
				is_error=True,
			)

	def on_data_read(self, message: ProcessDataReadMessage) -> None:
		if message.created < self.last_data_created:
			raise ValueError("Received ProcessDataReadMessage with older timestamp than previous ProcessDataReadMessage.")
		self.last_data_created = message.created

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
						prefix_color=self.prefix_color,
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
					prefix_color=self.prefix_color,
				)
				if buffer == self.stdout_buffer:
					self.stdout_buffer = bytearray()
				else:
					self.stderr_buffer = bytearray()


class ProcessMessagebusConnection(MessagebusConnection):
	COLORS = [
		c for c in ANSI_COLOR_NAMES if "white" not in c and "black" not in c and "bright" not in c and "grey" not in c and "gray" not in c
	]

	def __init__(self) -> None:
		self.console = get_console()
		self.out_lock = Lock()
		self.show_host_names = False
		self.max_host_name_length = 0
		self.data_encoding = "auto"
		self.output_encoding = "cp437" if is_windows() else "utf-8"
		self.processes: dict[str, MessagebusProcess] = {}
		self.color_position = 0
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

	def get_host_name(self, process_id: str) -> str | None:
		if process := self.processes.get(process_id):
			return process.host_name
		return None

	def write_out(
		self,
		*,
		data: bytes,
		stream: Literal["stdout", "stderr"],
		data_encoding: str | None,
		host_name: str | None = None,
		prefix_color: Color | None = None,
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
				line_prefix = f"{host_name} | "
				if prefix_color:
					ansi = ";".join(prefix_color.get_ansi_codes(foreground=True))
					line_prefix = f"\x1b[1;{ansi};22m{line_prefix}\x1b[0m"
				b_line_prefix = line_prefix.encode(use_encoding or self.output_encoding)
				lines = data.split(b"\n")
				last_idx = len(lines) - 1
				data = b"\n".join(b_line_prefix + line if idx != last_idx else line for idx, line in enumerate(lines))

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
		start_timeout = PROCESS_START_TIMEOUT
		if timeout > 0 and timeout < start_timeout:
			start_timeout = timeout

		self.processes = {}

		uniq_channels = list(set(channels))
		if len(uniq_channels) != len(channels):
			raise RuntimeError("Duplicate channels in list of channels.")

		stdin_data = bytearray(read_input_raw_bin())

		color = "NO_COLOR" not in os.environ
		for channel in channels:
			prefix_color = Color.parse(self.COLORS[self.color_position]) if color else None
			self.color_position += 1
			if self.color_position >= len(self.COLORS):
				self.color_position = 0
			message = ProcessStartRequestMessage(
				command=command,
				sender=CONNECTION_USER_CHANNEL,
				channel=channel,
				shell=shell,
			)
			self.processes[message.process_id] = MessagebusProcess(
				process_id=message.process_id,
				write_function=self.write_out,
				send_message=self.send_message,
				start_request=message,
				prefix_color=prefix_color,
				stdin_data=stdin_data,
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
					self.send_message(
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
				self.send_message(waiting_processes[idx].start_request)

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
	shell: str | None

	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self._should_close = Event()
		self._terminal_write_channel: str | None = None
		self._terminal_read_channel: str | None = None
		self._terminal_open_event = Event()
		self._terminal_error: Exception | None = None
		self._ctrl_c_times: list[float] = []
		self._application_mode = False
		self._is_windows = is_windows()

	def _on_terminal_open_event(self, message: TerminalOpenEventMessage) -> None:
		if message.terminal_id != self.terminal_id:
			logger.error("Received message for invalid terminal id: %s", message.to_dict())
			return
		self._terminal_write_channel = message.back_channel
		self._terminal_open_event.set()

	def _on_terminal_data_read(self, message: TerminalDataReadMessage) -> None:
		if message.terminal_id != self.terminal_id:
			logger.error("Received message for invalid terminal id: %s", message.to_dict())
			return

		if self._is_windows:
			chars = list(message.data)
			for idx, char in enumerate(chars):
				if char == 27 and chars[idx + 1] == 91 and chars[idx + 2] == 63 and chars[idx + 3] == 49:
					# ESC[?1
					if chars[idx + 4] == 104:
						if not self._application_mode:
							logger.debug("Enter application mode")
							self._application_mode = True
					else:
						if self._application_mode:
							logger.debug("Exit application mode")
							self._application_mode = False
			sys.stdout.buffer.write(message.data)
			sys.stdout.flush()
		else:
			sys.stdout.buffer.write(message.data)
			sys.stdout.flush()

	def _on_terminal_error(self, message: TerminalErrorMessage) -> None:
		if message.terminal_id != self.terminal_id:
			logger.error("Received message for invalid terminal id: %s", message.to_dict())
			return
		error = f"Received terminal error: {message.error.message}"
		logger.error(error)
		self._terminal_error = RuntimeError(message.error.message)
		self.initial_subscription_event.set()
		self._terminal_open_event.set()

	def _on_general_error(self, message: GeneralErrorMessage) -> None:
		error = f"Received general error: {message.error.message}"
		logger.error(error)
		self._terminal_error = RuntimeError(message.error.message)
		self.initial_subscription_event.set()
		self._terminal_open_event.set()

	def _on_terminal_close_event(self, message: TerminalCloseEventMessage) -> None:
		if message.terminal_id != self.terminal_id:
			logger.error("Received message for invalid terminal id: %s", message.to_dict())
			return
		logger.notice("Received terminal close event - shutting down")
		self.close("Terminal closed by remote")

	def _on_resize(self, signum: int = 0, frame: FrameType | None = None) -> None:
		assert self._terminal_write_channel
		size = shutil.get_terminal_size()
		message = TerminalResizeRequestMessage(
			sender=CONNECTION_USER_CHANNEL,
			channel=self._terminal_write_channel,
			terminal_id=self.terminal_id,
			rows=size.lines,
			cols=size.columns,
		)
		logger.notice("Requesting to resize terminal with id %s (rows=%d, cols=%d)", self.terminal_id, size.lines, size.columns)
		self.send_message(message)

	def open_terminal(self, channel: str) -> None:
		self._terminal_read_channel = f"session:{self.terminal_id}"
		self.subscribe_to_channel(self._terminal_read_channel)
		size = shutil.get_terminal_size()
		message = TerminalOpenRequestMessage(
			sender=CONNECTION_USER_CHANNEL,
			channel=channel,
			terminal_id=self.terminal_id,
			back_channel=self._terminal_read_channel,
			rows=size.lines,
			cols=size.columns,
			shell=self.shell,
		)
		logger.notice("Requesting to open terminal with id %s", self.terminal_id)
		self.send_message(message)

		if not self._terminal_open_event.wait(CHANNEL_SUB_TIMEOUT) or self._terminal_write_channel is None:
			if not self._terminal_error:
				self._terminal_error = ConnectionError("Timed out waiting for terminal to open")
		self._terminal_open_event.clear()  # Prepare for catching the next terminal_open_event

	def close(self, message: str) -> None:
		self._should_close.set()
		sys.stdout.write(f"\r\n> {message} <\r\n")

	def run_terminal(self, target: str, terminal_id: str | None = None, shell: str | None = None) -> None:
		target = target.lower()
		self.terminal_id = terminal_id or str(uuid4())
		self.shell = shell

		self.service_client.connect()
		connected_host_ids = self.service_client.host_getMessagebusConnectedIds()  # type: ignore[attr-defined]
		depots = self.service_client.host_getObjects(attributes=["id", "type"], type="OpsiDepotserver")  # type: ignore[attr-defined]
		configserver_id = [depot.id for depot in depots if depot.getType() == "OpsiConfigserver"][0]
		depotserver_ids = [depot.id for depot in depots]

		logger.debug("Connected host IDs: %s", connected_host_ids)
		logger.debug("Configserver ID: %s", configserver_id)
		logger.debug("Depotserver IDs: %s", depotserver_ids)

		host_id = forceHostId(configserver_id if target == "configserver" else target)
		if host_id != configserver_id and host_id not in connected_host_ids:
			raise ConnectionError(f"Host {host_id} is currently not connected to messagebus")

		if host_id in depotserver_ids:
			channel = f"service:depot:{host_id}:terminal"
		else:
			channel = f"host:{host_id}"

		if not self._is_windows:
			flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
			fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
			selector = selectors.DefaultSelector()
			selector.register(sys.stdin, selectors.EVENT_READ)

			signal(SIGWINCH, self._on_resize)

		with self.connection():
			self.open_terminal(channel)
			if self._terminal_error:
				raise self._terminal_error
			if self._should_close.is_set():
				return
			assert self._terminal_write_channel
			logger.notice("Return to local shell with 'exit' or 'Ctrl+D'")
			with raw_terminal():
				if self._is_windows:
					con_buf_in = win32console.GetStdHandle(-10)  # STD_INPUT_HANDLE /  CONIN$

				while not self._should_close.is_set():
					if self._terminal_error:
						raise self._terminal_error
					data = b""
					if self._is_windows:
						if con_buf_in.GetNumberOfConsoleInputEvents() == 0:
							time.sleep(0.005)
							continue
						for event in con_buf_in.ReadConsoleInput(1024):
							# https://timgolden.me.uk/pywin32-docs/PyINPUT_RECORD.html
							if event.EventType == 1:  # KEY_EVENT
								if event.KeyDown:
									# https://www.gnu.org/software/screen/manual/html_node/Input-Translation.html
									mchr = b"O" if self._application_mode else b"["
									if event.VirtualScanCode == 72:  # Cursor up
										data += b"\033" + mchr + b"A"
									elif event.VirtualScanCode == 80:  # Cursor down
										data += b"\033" + mchr + b"B"
									elif event.VirtualScanCode == 77:  # Cursor right
										data += b"\033" + mchr + b"C"
									elif event.VirtualScanCode == 75:  # Cursor left
										data += b"\033" + mchr + b"D"
									elif event.VirtualScanCode == 71:  # Pos 1
										data += b"\033[H"
									elif event.VirtualScanCode == 79:  # End
										data += b"\033[F"
									elif event.VirtualScanCode == 73:  # Page up
										data += b"\033[5~"
									elif event.VirtualScanCode == 81:  # Page down
										data += b"\033[6~"
									else:
										data += event.Char.encode("utf-8")
							elif event.EventType == 4:  # WINDOW_BUFFER_SIZE_EVENT
								self._on_resize()
						if not data:
							continue
					else:
						if not selector.select(0.005):
							continue
						data = sys.stdin.buffer.read()

					if not data:
						self._should_close.set()
						break

					if data == b"\x03":  # Ctrl+C
						now = time.time()
						self._ctrl_c_times = [t for t in self._ctrl_c_times if t > now - 1]
						self._ctrl_c_times.append(now)
						if len(self._ctrl_c_times) > 3:
							logger.notice("Ctrl+C was pressed 3 times in a second - closing terminal")
							self._should_close.set()
							break

					message = TerminalDataWriteMessage(
						sender=CONNECTION_USER_CHANNEL,
						channel=self._terminal_write_channel,
						terminal_id=self.terminal_id,
						data=data,
					)
					self.send_message(message)
