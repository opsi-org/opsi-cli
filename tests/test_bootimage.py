# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import json

import pytest
from opsi.opsi.service.client import ServiceClient
from purecrypt import Crypt

from opsicli.utils import random_string

from .utils import run_cli, tmp_client

CLIENT1 = "pytest-client1.test.tld"


@pytest.mark.opsi_service
def test_bootimage_set_boot_parameter(admin_service_client: ServiceClient) -> None:
	exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "nomodeset"])
	assert exit_code == 0
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "netboot.linux-bootimage.cmdline.nomodeset"}])
	assert configs[0].defaultValues == [True]
	exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "lang", "de"])
	assert exit_code == 0
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "netboot.linux-bootimage.cmdline.lang"}])
	assert configs[0].defaultValues == ["de"]


@pytest.mark.opsi_service
def test_bootimage_set_boot_parameter_client(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT1):
		exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "nomodeset"])
		assert exit_code == 0
		config_states = admin_service_client.jsonrpc(
			"configState_getObjects", params=[[], {"configId": "netboot.linux-bootimage.cmdline.nomodeset", "objectId": CLIENT1}]
		)
		assert config_states[0].values == [True]
		exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "lang", "de"])
		assert exit_code == 0
		config_states = admin_service_client.jsonrpc(
			"configState_getObjects", params=[[], {"configId": "netboot.linux-bootimage.cmdline.lang", "objectId": CLIENT1}]
		)
		assert config_states[0].values == ["de"]


@pytest.mark.opsi_service
def test_bootimage_set_boot_password(admin_service_client: ServiceClient) -> None:
	password = random_string(10)
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", password])
	print(stdout)
	assert exit_code == 0
	password_hash = json.loads(stdout)["password_hash"]

	assert Crypt.is_valid(password, password_hash)

	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "netboot.linux-bootimage.cmdline.pwh"}])
	assert configs[0].defaultValues == [password_hash]


@pytest.mark.opsi_service
def test_bootimage_remove_boot_password(admin_service_client: ServiceClient) -> None:
	password = random_string(10)
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", password])
	print(stdout)
	assert exit_code == 0
	first_password_hash = json.loads(stdout)["password_hash"]

	assert Crypt.is_valid(password, first_password_hash)

	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "netboot.linux-bootimage.cmdline.pwh"}])
	assert configs[0].defaultValues == [first_password_hash]

	password = random_string(10)
	exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", password])
	print(stdout)
	assert exit_code == 0
	second_password_hash = json.loads(stdout)["password_hash"]

	assert Crypt.is_valid(password, second_password_hash)
	configs = admin_service_client.jsonrpc("config_getObjects", params=[[], {"id": "netboot.linux-bootimage.cmdline.pwh"}])
	assert configs[0].defaultValues == [second_password_hash]
