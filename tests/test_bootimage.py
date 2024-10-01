"""
test crypto plugin
"""

import pytest
from purecrypt import Crypt  # type: ignore[import]

from opsicli.opsiservice import get_service_connection

from .utils import container_connection, run_cli, tmp_client

CLIENT1 = "pytest-client1.test.tld"


@pytest.mark.requires_testcontainer
def test_bootimage_set_boot_parameter() -> None:
	with container_connection():
		connection = get_service_connection()
		exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "nomodeset"])
		assert exit_code == 0
		configs = connection.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
		assert "nomodeset" in configs[0].defaultValues
		exit_code, _stdout, _stderr = run_cli(["bootimage", "set-boot-parameter", "lang", "de"])
		assert exit_code == 0
		configs = connection.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
		assert "lang=de" in configs[0].defaultValues


@pytest.mark.requires_testcontainer
def test_bootimage_set_boot_parameter_client() -> None:
	with container_connection():
		connection = get_service_connection()
		with tmp_client(connection, CLIENT1):
			exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "nomodeset"])
			assert exit_code == 0
			config_states = connection.jsonrpc(
				"configState_getObjects", params=[[], {"configId": "opsi-linux-bootimage.append", "objectId": CLIENT1}]
			)
			assert "nomodeset" in config_states[0].values
			exit_code, _stdout, _stderr = run_cli(["bootimage", "--client", CLIENT1, "set-boot-parameter", "lang", "de"])
			assert exit_code == 0
			config_states = connection.jsonrpc(
				"configState_getObjects", params=[[], {"configId": "opsi-linux-bootimage.append", "objectId": CLIENT1}]
			)
			assert "lang=de" in config_states[0].values


@pytest.mark.requires_testcontainer
def test_bootimage_set_boot_password() -> None:
	with container_connection():
		connection = get_service_connection()
		exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "linux123"])
		assert exit_code == 0
		split_length = len("Hashed password is: ")
		result = stdout.split("\n")[0][split_length:]
		print(result)
		assert Crypt.is_valid("linux123", result)
		configs = connection.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
		assert f"pwh={result}" in configs[0].defaultValues


@pytest.mark.requires_testcontainer
def test_bootimage_remove_boot_password() -> None:
	with container_connection():
		connection = get_service_connection()
		exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "linux123"])
		assert exit_code == 0
		split_length = len("Hashed password is: ")
		result_first_hash = stdout.split("\n")[0][split_length:]
		print(result)
		assert Crypt.is_valid("linux123", result_first_hash)
		configs = connection.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
		assert f"pwh={result_first_hash}" in configs[0].defaultValues
		exit_code, stdout, _stderr = run_cli(["bootimage", "set-boot-password", "nt123"])
		assert exit_code == 0
		split_length = len("Hashed password is: ")
		result_second_hash = stdout.split("\n")[0][split_length:]
		print(result_second_hash)
		assert Crypt.is_valid("nt123", result_second_hash)
		configs = connection.jsonrpc("config_getObjects", params=[[], {"id": "opsi-linux-bootimage.append"}])
		assert f"pwh={result_second_hash}" in configs[0].defaultValues
		assert f"pwh={result_first_hash}" not in configs[0].defaultValues
