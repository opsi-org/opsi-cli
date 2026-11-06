# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_messagebus
"""

import json
import time
from contextlib import chdir, nullcontext
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from opsi.logging import get_logger, log_context
from opsi.opsi.messagebus import (
	CONNECTION_USER_CHANNEL,
	ChannelSubscriptionEventMessage,
	EventMessage,
	FileChunkMessage,
	FileDownloadInformationMessage,
	FileDownloadRequestMessage,
	FileUploadRequestMessage,
	FileUploadResponseMessage,
	FileUploadResultMessage,
	Message,
)
from opsi.opsi.service.client import ServiceClient

from opsicli.messagebus import (
	CHANNEL_SUB_TIMEOUT,
	DEFAULT_START_TIMEOUT,
	MESSAGEBUS_DISCONNECT_TIMEOUT,
	JSONRPCMessagebusConnection,
	MessagebusConnection,
	MessagebusListener,
)
from opsicli.opsiservice import get_service_connection

from .conftest import get_admin_service_client, get_host_service_client
from .utils import admin_service_config, run_cli, tmp_client, tmp_product

logger = get_logger()


@pytest.mark.parametrize("started, completed", [(False, False), (True, False), (True, True), (False, True)])
def test_installation_event_timeouts(started: bool, completed: bool) -> None:
	from plugins.messagebus.python import EventMessagebusConnection

	with patch("opsicli.messagebus.get_service_connection", return_value=MagicMock(spec=ServiceClient)):
		connection = EventMessagebusConnection()
	start_data = {"clientId": "client1.test.tld", "productId": "testproduct", "installationStatus": "unknown"}
	completed_data = dict(start_data, installationStatus="installed", actionResult="successful")

	def receive_events(timeout: float) -> bool:
		assert timeout == 120
		connection._on_event(EventMessage(sender="service:messagebus", channel="event:host_updated", event="host_updated", data=start_data))
		connection._on_event(
			EventMessage(
				sender="service:messagebus",
				channel="event:productOnClient_updated",
				event="productOnClient_updated",
				data=dict(start_data, clientId="other.test.tld"),
			)
		)
		assert not connection.event_started_event.is_set()
		if started:
			connection._on_event(
				EventMessage(
					sender="service:messagebus", channel="event:productOnClient_updated", event="productOnClient_updated", data=start_data
				)
			)
		if completed:
			connection._on_event(
				EventMessage(
					sender="service:messagebus",
					channel="event:productOnClient_updated",
					event="productOnClient_updated",
					data=completed_data,
				)
			)
		return connection.event_started_event.is_set()

	with (
		patch.object(connection, "connection", return_value=nullcontext()),
		patch.object(connection, "subscribe_to_channel") as subscribe,
		patch.object(connection.event_started_event, "wait", side_effect=receive_events),
		patch.object(connection.event_found_event, "wait", return_value=completed) as completion_wait,
	):
		if completed:
			result = connection.wait_for_event(
				type="productOnClient_updated", data_all=[completed_data], start_data=[start_data], start_timeout=120, timeout=10
			)
			assert [message.data for message in result] == [completed_data]
		else:
			with pytest.raises(TimeoutError, match="start event" if not started else "event"):
				connection.wait_for_event(
					type="productOnClient_updated", data_all=[completed_data], start_data=[start_data], start_timeout=120, timeout=10
				)
		subscribe.assert_called_once_with(["event:productOnClient_updated"])
		if started or completed:
			completion_wait.assert_called_once_with(10)
		else:
			completion_wait.assert_not_called()


@pytest.mark.parametrize("start_timeout", [None, "2.5"])
@pytest.mark.parametrize("outcome", ["successful", "failed", "start_timeout", "completion_timeout"])
def test_wait_for_installation_options(start_timeout: str | None, outcome: str) -> None:
	from plugins.messagebus.python import EventMessagebusConnection, wait_for_installation

	args = ["client1.test.tld", "testproduct", "otherproduct", "--timeout", "10"]
	if start_timeout is not None:
		args.extend(["--start-timeout", start_timeout])
	with patch("plugins.messagebus.python.EventMessagebusConnection", spec=EventMessagebusConnection) as connection:
		wait = connection.return_value.wait_for_event
		if outcome.endswith("timeout"):
			wait.side_effect = TimeoutError("start event" if outcome == "start_timeout" else "completion event")
		else:
			wait.return_value = [
				EventMessage(
					sender="service:messagebus",
					channel="event:productOnClient_updated",
					event="productOnClient_updated",
					data={"installationStatus": "installed" if outcome == "successful" else "unknown", "actionResult": outcome},
				)
			]
		result = CliRunner(mix_stderr=False).invoke(wait_for_installation, args)
		assert result.exit_code == (0 if outcome == "successful" else 1)
		assert wait.call_count == 1
		assert wait.call_args.kwargs["start_timeout"] == (DEFAULT_START_TIMEOUT if start_timeout is None else float(start_timeout))
		assert wait.call_args.kwargs["timeout"] == 10
		assert wait.call_args.kwargs["start_data"] == [
			{"clientId": "client1.test.tld", "productId": product, "installationStatus": "unknown"}
			for product in ("testproduct", "otherproduct")
		]
		if outcome.endswith("timeout"):
			assert isinstance(result.exception, RuntimeError)
			assert ("start event" if outcome == "start_timeout" else "completion event") in str(result.exception)
		else:
			assert json.loads(result.stdout)["actionResult"] == outcome


@pytest.mark.parametrize("fail_in_context", (False, True))
def test_messagebus_waits_for_disconnect(fail_in_context: bool) -> None:
	service_client = MagicMock(spec=ServiceClient)
	service_client.messagebus_connected = False
	with patch("opsicli.messagebus.get_service_connection", return_value=service_client):
		connection = MessagebusConnection()
	connection.connection_closed_event.set()

	def connect() -> None:
		service_client.messagebus_connected = True
		connection._on_channel_subscription_event(
			ChannelSubscriptionEventMessage(sender="service:messagebus", channel="session:test", subscribed_channels=["session:test"])
		)

	def disconnect() -> None:
		service_client.messagebus_connected = False

	def wait_for_close(timeout: float) -> bool:
		service_client.disconnect_messagebus.assert_called_once()
		service_client.messagebus.unregister_messagebus_listener.assert_not_called()
		# No reconnect delay must be scheduled by the close callback of a deliberate disconnect
		assert service_client.messagebus.reconnect_wait_min == 0
		assert service_client.messagebus.reconnect_wait_max == 0
		assert not connection.connection_closed_event.is_set()
		connection.messagebus_connection_closed(service_client.messagebus)
		return connection.connection_closed_event.is_set()

	service_client.messagebus.reconnect_wait_min = 5
	service_client.messagebus.reconnect_wait_max = 10
	service_client.connect_messagebus.side_effect = connect
	service_client.disconnect_messagebus.side_effect = disconnect
	with patch.object(connection.connection_closed_event, "wait", side_effect=wait_for_close) as wait:
		if fail_in_context:
			with pytest.raises(RuntimeError, match="context failed"), connection.connection():
				raise RuntimeError("context failed")
		else:
			with connection.connection():
				pass
		wait.assert_called_once_with(MESSAGEBUS_DISCONNECT_TIMEOUT)
	service_client.messagebus.unregister_messagebus_listener.assert_called_once_with(connection)
	assert service_client.messagebus.reconnect_wait_min == 5
	assert service_client.messagebus.reconnect_wait_max == 10


def test_messagebus_disconnect_timeout() -> None:
	service_client = MagicMock(spec=ServiceClient)
	service_client.messagebus_connected = True
	service_client.messagebus.reconnect_wait_min = 5
	service_client.messagebus.reconnect_wait_max = 5
	with patch("opsicli.messagebus.get_service_connection", return_value=service_client):
		connection = MessagebusConnection()
	with (
		patch.object(connection.initial_subscription_event, "wait", return_value=True),
		patch.object(connection.connection_closed_event, "wait", return_value=False),
		patch("opsicli.messagebus.logger") as logger_mock,
		connection.connection(),
	):
		pass
	logger_mock.warning.assert_called_once()
	service_client.messagebus.unregister_messagebus_listener.assert_called_once_with(connection)
	assert service_client.messagebus.reconnect_wait_min == 5
	assert service_client.messagebus.reconnect_wait_max == 5


def test_messagebus_reconnect_clears_subscriptions() -> None:
	service_client = MagicMock(spec=ServiceClient)
	service_client.messagebus_connected = True
	service_client.messagebus.reconnect_wait_min = 5
	service_client.messagebus.reconnect_wait_max = 5
	with patch("opsicli.messagebus.get_service_connection", return_value=service_client):
		connection = MessagebusConnection()

	def connect() -> None:
		assert not connection.initial_subscription_event.is_set()
		assert not connection.subscribed_channels
		connection._on_channel_subscription_event(
			ChannelSubscriptionEventMessage(sender="service:messagebus", channel="session:test", subscribed_channels=["session:test"])
		)

	service_client.connect_messagebus.side_effect = connect
	service_client.disconnect_messagebus.side_effect = lambda: connection.messagebus_connection_closed(service_client.messagebus)
	for _ in range(2):
		with connection.connection():
			assert connection.subscribed_channels == ["session:test"]


def test_messagebus_nested_connection_keeps_subscription() -> None:
	service_client = MagicMock(spec=ServiceClient)
	service_client.messagebus_connected = False
	service_client.messagebus.reconnect_wait_min = 5
	service_client.messagebus.reconnect_wait_max = 5
	with patch("opsicli.messagebus.get_service_connection", return_value=service_client):
		connection = MessagebusConnection()

	def connect() -> None:
		# Like the real messagebus, connecting an already connected bus sends no new subscription event
		if service_client.messagebus_connected:
			return
		service_client.messagebus_connected = True
		connection._on_channel_subscription_event(
			ChannelSubscriptionEventMessage(sender="service:messagebus", channel="session:test", subscribed_channels=["session:test"])
		)

	def disconnect() -> None:
		service_client.messagebus_connected = False
		connection.messagebus_connection_closed(service_client.messagebus)

	service_client.connect_messagebus.side_effect = connect
	service_client.disconnect_messagebus.side_effect = disconnect
	with patch.object(connection.initial_subscription_event, "wait", wraps=connection.initial_subscription_event.wait) as wait:
		with connection.connection(), connection.connection():
			assert connection.subscribed_channels == ["session:test"]
		wait.assert_called_once_with(CHANNEL_SUB_TIMEOUT)
	assert not connection.initial_subscription_event.is_set()
	assert not connection.subscribed_channels


def test_messagebus_connected_by_other_connection_does_not_wait() -> None:
	service_client = MagicMock(spec=ServiceClient)
	service_client.messagebus_connected = True
	service_client.messagebus.reconnect_wait_min = 5
	service_client.messagebus.reconnect_wait_max = 5
	with patch("opsicli.messagebus.get_service_connection", return_value=service_client):
		connection = MessagebusConnection()
	service_client.disconnect_messagebus.side_effect = lambda: connection.messagebus_connection_closed(service_client.messagebus)
	with patch.object(connection.initial_subscription_event, "wait", return_value=False) as wait, connection.connection():
		pass
	wait.assert_not_called()


@pytest.mark.opsi_service
def test_messagebus_jsonrpc() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			assert connection
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
		assert "opsiVersion" in result


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_params() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
		assert len(result) == 1
		assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_error() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "method_which_does_not_exist")["service:config:jsonrpc"]
		assert "data" in result["error"]
		assert result["error"]["data"]["class"] == "ValueError"
		assert "Invalid method" in result["error"]["data"]["details"]


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_multiple() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
			assert "opsiVersion" in result
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
			assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"types, output_type",
	(
		([], None),
		(["host_created"], "message"),
	),
)
def test_get_events(types: list[str], output_type: str | None) -> None:
	client_id = "dummy1.test.tld"
	subscribe_to_channel = MessagebusConnection.subscribe_to_channel

	def subscribe_and_create_host(connection: MessagebusConnection, channel: str | list[str]) -> None:
		subscribe_to_channel(connection, channel)
		with get_admin_service_client() as client:
			client.jsonrpc("host_createOpsiClient", params=[client_id])
			client.jsonrpc("host_delete", params=[client_id])

	cmd = ["--output-format", "json", "messagebus", "get-events", "--timeout", "10"]
	for event_type in types:
		cmd += ["--type", event_type]
	if output_type:
		cmd += ["--output-type", output_type]

	with patch.object(MessagebusConnection, "subscribe_to_channel", subscribe_and_create_host):
		exit_code, _stdout, _stderr = run_cli(cmd)

	assert exit_code == 0, _stderr
	data = [json.loads(line.strip()) for line in _stdout.splitlines() if line]
	assert len(data) == (len(types) if types else 2)
	if output_type == "message":
		assert data[0]["sender"]
	else:
		assert "sender" not in data[0]


@pytest.mark.opsi_service
@pytest.mark.parametrize("with_data", (True, False))
def test_wait_for_event(with_data: bool) -> None:
	client_id = "dummy1.test.tld"

	class CreateHostThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "CreateHostThread"}), get_admin_service_client() as client:
				time.sleep(7)
				client.jsonrpc("host_createOpsiClient", params=[client_id])
				time.sleep(1)
				client.jsonrpc("host_delete", params=[client_id])

	for cid in (client_id, "some.other.host"):
		cht = CreateHostThread(daemon=True)
		cht.start()
		cmd = ["messagebus", "wait-for-event", "host_created", "--timeout", "10"]
		if with_data:
			cmd += ["--data", f"id={cid}"]
		exit_code, stdout, stderr = run_cli(cmd)
		cht.join()
		if with_data and cid != client_id:
			# Timeout reached
			assert exit_code == 1
			assert "Timed out after waiting 10.0 seconds for the event" in stderr
		else:
			# 'host_created' event found
			assert exit_code == 0
			data = json.loads(stdout)
			assert data["type"] == "OpsiClient"
			assert data["id"] == client_id


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"installation_status, action_result",
	[
		("installed", "successful"),
		("not_installed", "failed"),
		("installed", None),
	],
)
def test_wait_for_installation(installation_status: str, action_result: str | None) -> None:
	# action_result == None => timeout
	class FakeInstallationThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "FakeInstallationThread"}), get_admin_service_client() as client:
				time.sleep(7)
				if action_result is None:
					time.sleep(5)
				else:
					client.jsonrpc(
						"productOnClient_updateObjects",
						params=[
							{
								"clientId": "client1.test.tld",
								"productId": "testproduct",
								"actionResult": action_result,
								"installationStatus": installation_status,
								"productType": "LocalbootProduct",
							}
						],
					)

	with (
		admin_service_config(),
		get_service_connection() as connection,
		tmp_client(connection, "client1.test.tld"),
		tmp_product(connection, "testproduct"),
	):
		cht = FakeInstallationThread(daemon=True)
		cht.start()
		cmd = [
			"messagebus",
			"wait-for-installation",
			"client1.test.tld",
			"testproduct",
			"--installation-status",
			installation_status,
			"--timeout",
			"10",
		]
		exit_code, _stdout, _stderr = run_cli(cmd)
		if action_result is None:
			assert "Timed out after waiting" in _stderr
		cht.join()
		assert exit_code == 0 if action_result == "successful" else 1


@pytest.mark.opsi_service
def test_wait_for_host() -> None:
	class FakeHostConnectionThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "FakeHostConnectionThread"}):
				time.sleep(2)
				with get_host_service_client("client1.test.tld", "00000000000000000000000000000000") as client:
					client.connect_messagebus()

	with (
		admin_service_config(),
		get_service_connection() as connection,
		tmp_client(connection, "client1.test.tld", "00000000000000000000000000000000"),
	):
		thread = FakeHostConnectionThread(daemon=True)
		thread.start()
		cmd = [
			"messagebus",
			"wait-for-host",
			"client1.test.tld",
			"--timeout",
			"10",
		]
		exit_code, _stdout, _stderr = run_cli(cmd)
		thread.join()
		assert exit_code == 0


@pytest.mark.opsi_service
def test_download(tmp_path: Path) -> None:
	class TestDownloadMessagebusListener(MessagebusListener):
		def message_received(self, message: Message) -> None:
			assert self.messagebus
			# print(f"Message received: {message.to_dict()}")
			if isinstance(message, FileDownloadRequestMessage):
				self.messagebus.send_message(
					FileDownloadInformationMessage(sender=CONNECTION_USER_CHANNEL, channel=message.response_channel, size=12)
				)
				self.messagebus.send_message(
					FileChunkMessage(sender=CONNECTION_USER_CHANNEL, channel=message.response_channel, data=b"chunk1", number=1, last=False)
				)
				self.messagebus.send_message(
					FileChunkMessage(sender=CONNECTION_USER_CHANNEL, channel=message.response_channel, data=b"chunk2", number=2, last=True)
				)

	class FakeHostConnectionThread(Thread):
		should_stop = False

		def run(self) -> None:
			with (
				log_context({"instance": "FakeHostConnectionThread"}),
				get_host_service_client("client1.test.tld", "00000000000000000000000000000000") as client,
			):
				listener = TestDownloadMessagebusListener(client.messagebus)
				client.messagebus.register_messagebus_listener(listener)
				client.connect_messagebus()
				while not self.should_stop:
					time.sleep(1)

	destination_file = tmp_path / "file.txt"
	with (
		chdir(tmp_path),
		admin_service_config(),
		get_service_connection() as connection,
		tmp_client(connection, "client1.test.tld", "00000000000000000000000000000000"),
	):
		thread = FakeHostConnectionThread(daemon=True)
		thread.start()
		time.sleep(2)
		for dest in None, "-", destination_file, destination_file.parent:
			print("Downloading to", dest)
			cmd = [
				"messagebus",
				"download",
				"client1.test.tld",
				"/path/to/source/file.txt",
			]
			if dest is not None:
				cmd.append(str(dest))
			exit_code, stdout, stderr = run_cli(cmd)

			assert exit_code == 0
			assert "File '/path/to/source/file.txt' downloaded successfully to" in stderr.replace("\n", "")
			if dest == "-":
				assert stdout == "chunk1chunk2"
			else:
				assert stdout == ""
				assert destination_file.read_bytes() == b"chunk1chunk2"
				destination_file.unlink()

		thread.should_stop = True
		thread.join()


@pytest.mark.opsi_service
@pytest.mark.parametrize("source", ("-", "file.txt"))
def test_upload(tmp_path: Path, source: str) -> None:
	class TestUploadMessagebusListener(MessagebusListener):
		def message_received(self, message: Message) -> None:
			assert self.messagebus
			# print(f"Message received: {message.to_dict()}")
			if isinstance(message, FileUploadRequestMessage):
				self.messagebus.send_message(
					FileUploadResponseMessage(sender=CONNECTION_USER_CHANNEL, channel=message.response_channel, path="/remote/path")
				)
			elif isinstance(message, FileChunkMessage) and message.last:
				self.messagebus.send_message(
					FileUploadResultMessage(sender=CONNECTION_USER_CHANNEL, channel=message.response_channel, path="/remote/path")
				)

	class FakeHostConnectionThread(Thread):
		should_stop = False

		def run(self) -> None:
			with (
				log_context({"instance": "FakeHostConnectionThread"}),
				get_host_service_client("client1.test.tld", "00000000000000000000000000000000") as client,
			):
				listener = TestUploadMessagebusListener(client.messagebus)
				client.messagebus.register_messagebus_listener(listener)
				client.connect_messagebus()
				while not self.should_stop:
					time.sleep(1)

	source_file = tmp_path / "file.txt"
	source_file.write_bytes(b"data")
	with (
		chdir(tmp_path),
		admin_service_config(),
		get_service_connection() as connection,
		tmp_client(connection, "client1.test.tld", "00000000000000000000000000000000"),
	):
		thread = FakeHostConnectionThread(daemon=True)
		thread.start()
		try:
			time.sleep(2)
			src = "-" if source == "-" else source_file
			print("Uploading", src)
			cmd = [
				"messagebus",
				"upload",
				"client1.test.tld",
				str(src),
				"/path/to/destination/file.txt",
			]
			exit_code, stdout, stderr = run_cli(cmd, stdin=(["data"] if src == "-" else None))

			assert exit_code == 0
			assert f"File '{src}' uploaded successfully to '/remote/path'" in stderr.replace("\n", "")
			assert stdout == ""
		finally:
			thread.should_stop = True
			thread.join()
