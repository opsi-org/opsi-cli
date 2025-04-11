# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_terminal
"""

import pytest

from opsicli.messagebus import TerminalMessagebusConnection

from .utils import admin_service_config


@pytest.mark.opsi_service
def test_messagebus_terminal() -> None:
	with admin_service_config():
		connection = TerminalMessagebusConnection()
		with connection.connection():
			connection.open_terminal("configserver")


@pytest.mark.opsi_service
def test_messagebus_reconnect() -> None:
	with admin_service_config():
		for iteration in range(2):
			connection = TerminalMessagebusConnection()
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.connection():
				print(f"Iteration {iteration} getting channel pair")
				connection.open_terminal("configserver")
