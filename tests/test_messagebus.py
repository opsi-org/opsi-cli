# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_messagebus
"""

import json
import time
from contextlib import chdir
from pathlib import Path
from threading import Thread

import pytest
from opsi.logging import get_logger, log_context
from opsi.opsi.messagebus import (
	CONNECTION_USER_CHANNEL,
	FileChunkMessage,
	FileDownloadInformationMessage,
	FileDownloadRequestMessage,
	FileUploadRequestMessage,
	FileUploadResponseMessage,
	FileUploadResultMessage,
	Message,
)

from opsicli.messagebus import JSONRPCMessagebusConnection, MessagebusListener
from opsicli.opsiservice import get_service_connection

from .conftest import get_admin_service_client, get_host_service_client
from .utils import admin_service_config, run_cli, tmp_client, tmp_product

logger = get_logger()


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
		cmd = ["--output-format", "json", "messagebus", "get-events", "--timeout", "10"]
		for event_type in types:
			cmd += ["--type", event_type]
		if output_type:
			cmd += ["--output-type", output_type]

		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		data = [json.loads(line.strip()) for line in _stdout.splitlines() if line]
		assert len(data) == len(types) if types else 2
		if output_type == "message":
			assert data[0]["sender"]
		else:
			assert "sender" not in data[0]
		assert exit_code == 0


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
def test_upload(tmp_path: Path) -> None:
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
		time.sleep(2)
		for src in "-", source_file:
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

		thread.should_stop = True
		thread.join()
