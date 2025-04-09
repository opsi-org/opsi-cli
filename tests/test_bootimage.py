# -*- coding: utf-8 -*-

# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test crypto plugin
"""

import pytest
from opsicommon.client.opsiservice import ServiceClient
from purecrypt import Crypt  # type: ignore[import]

from .utils import run_cli, tmp_client

CLIENT1 = "pytest-client1.test.tld"


@pytest.mark.opsi_service
def test_bootimage_set_boot_parameter(admin_service_client: ServiceClient) -> None:
	exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "nomodeset"])
	assert exit_code == 0
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
	assert "nomodeset" in configs[0].defaultValues
	exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "lang", "de"])
	assert exit_code == 0
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
	assert "lang=de" in configs[0].defaultValues


@pytest.mark.opsi_service
def test_bootimage_set_boot_parameter_client(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT1):
		exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "nomodeset"])
		assert exit_code == 0
		config_states = admin_service_client.jsonrpc(
			"configState_getObjects", params=[[], {"configId": "opsi-linux-bootimage.append", "objectId": CLIENT1}]
		)
		assert "nomodeset" in config_states[0].values
		exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "lang", "de"])
		assert exit_code == 0
		config_states = admin_service_client.jsonrpc(
			"configState_getObjects", params=[[], {"configId": "opsi-linux-bootimage.append", "objectId": CLIENT1}]
		)
		assert "lang=de" in config_states[0].values


@pytest.mark.opsi_service
def test_bootimage_set_boot_password(admin_service_client: ServiceClient) -> None:
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "linux123"])
	assert exit_code == 0
	split_length = len("Hashed password is: ")
	result = stdout.split("\n")[0][split_length:]
	print(result)
	assert Crypt.is_valid("linux123", result)
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
	assert f"pwh={result}" in configs[0].defaultValues


@pytest.mark.opsi_service
def test_bootimage_remove_boot_password(admin_service_client: ServiceClient) -> None:
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "linux123"])
	assert exit_code == 0
	split_length = len("Hashed password is: ")
	result_first_hash = stdout.split("\n")[0][split_length:]
	print(result_first_hash)
	assert Crypt.is_valid("linux123", result_first_hash)
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
	assert f"pwh={result_first_hash}" in configs[0].defaultValues
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "nt123"])
	assert exit_code == 0
	split_length = len("Hashed password is: ")
	result_second_hash = stdout.split("\n")[0][split_length:]
	print(result_second_hash)
	assert Crypt.is_valid("nt123", result_second_hash)
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
	assert f"pwh={result_second_hash}" in configs[0].defaultValues
	assert f"pwh={result_first_hash}" not in configs[0].defaultValues
