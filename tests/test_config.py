"""
test_config
"""

import sys
from pathlib import Path
from typing import Type

import pytest
from ruamel.yaml import YAML  # noqa: E402  # type: ignore[import]

from opsicli.config import Config, ConfigItem
from opsicli.types import Bool, Directory, LogLevel, OPSIServiceUrl, Password

from .conftest import PLATFORM
from .utils import run_cli, temp_context


@pytest.mark.parametrize(
	"default, value, expected",
	((None, None, None), ("1", None, 1), (1, 10, 10), (None, 1, 1)),
)
def test_config_item_defaults(default: str | None, value: int | None, expected: int | None) -> None:
	item = ConfigItem(name="test", type=int, default=default, value=value)
	assert item.value == expected


@pytest.mark.parametrize(
	"value, expected, exception",
	(
		(None, None, None),
		("1", 1, None),
		("warning", 4, None),
		("0", 0, None),
		("-1", 0, None),
		(10, 9, None),
		("invalid", None, ValueError),
	),
)
def test_config_item_log_level(value: str | int | None, expected: int | None, exception: Type[Exception] | None) -> None:
	item = ConfigItem(name="log_level_file", type=LogLevel)
	if exception:
		with pytest.raises(exception):
			item.value = value
	else:
		item.value = value
		assert item.value == expected


@pytest.mark.parametrize(
	"value, expected",
	((None, None), ("1", True), (True, True), (False, False), ("true", True), ("TRUE", True), ("false", False), ("FALSE", False)),
)
def test_config_item_bool(value: str | None, expected: bool | None) -> None:
	item = ConfigItem(name="color", type=Bool, value=value)
	assert item.value == expected


@pytest.mark.parametrize(
	"value, expected",
	(
		("localhost", "https://localhost:4447"),
		("10.10.10.10:443", "https://10.10.10.10:443"),
		("https://[2a02:810b:f3f:fa4b:7170:26c0:c849:6e33]", "https://[2a02:810b:f3f:fa4b:7170:26c0:c849:6e33]:4447"),
	),
)
def test_config_item_opsi_service(value: str, expected: str) -> None:
	item = ConfigItem(name="service", type=OPSIServiceUrl, value=value)
	# as_dict produces Dict containing Dict of values being Dicts with the actual value
	assert item.as_dict()["value"].get("value") == expected
	assert item.value == expected


def test_config_item_password() -> None:
	item = ConfigItem(name="password", type=Password, value="password123")
	assert item.value == "password123"
	assert f"{item.value!r}" == "***secret***"


def test_config_item_plugin_user_dir() -> None:
	if PLATFORM == "windows":
		item = ConfigItem(name="plugin_user_dir", type=Directory, value=r"C:\path1")
		assert item.value == Path(r"C:\path1")
	elif PLATFORM in ("linux", "darwin"):
		item = ConfigItem(name="plugin_user_dir", type=Directory, value="/path1")
		assert item.value == Path("/path1")


def test_config_defaults() -> None:
	config = Config()
	assert config.color is True
	assert config.service is None


def test_set_config() -> None:
	config = Config()
	assert config.color is True
	config.color = "false"
	assert config.color is False
	assert config.get_config_item("color").default is True
	assert config.get_config_item("color").value is False


def test_read_write_config() -> None:
	config = Config()
	with temp_context() as tmp_path:
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile
		# Write any config value and save
		exit_code, stdout, _stderr = run_cli(["config", "set", "output_format", "csv"])
		print(stdout)
		assert exit_code == 0
		assert conffile.exists()
		config.set_values({"output_format": "msgpack"})
		# Load config from file and check if value is set
		config.read_config_files()
		print(config.get_values().get("output_format"))
		assert config.get_values().get("output_format") == "csv"
		assert config.output_format == "csv"
		exit_code, _stdout, _stderr = run_cli(["config", "unset", "output_format"])
		assert exit_code == 0
		config.read_config_files()
		assert config.get_values().get("output_format") == "auto"
		assert config.output_format == "auto"


def test_service_config() -> None:
	config = Config()

	with temp_context() as tmp_path:
		# config service add writes conffile. Explicitely set here to avoid wiping config file of the user.
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile
		exit_code, _stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test", "--username=testuser", "--password=testpassword", "https://testurl:4447"]
		)
		assert exit_code == 0
		assert any(service.name == "test" for service in config.get_values().get("services", []))
		exit_code, _stdout, _stderr = run_cli(["config", "service", "remove", "test"])
		assert exit_code == 0
		assert not any(service.name == "test" for service in config.get_values().get("services", []))


def test_config_service_add() -> None:
	config = Config()

	with temp_context() as tmp_path:
		# config service add writes conffile. Explicitely set here to avoid wiping config file of the user.
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile

		exit_code, stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test", "--username=testuser", "--password=testpassword", "testhost"]
		)
		assert exit_code == 0
		assert stdout == "Successfully added new service 'test' with URL 'https://testhost:4447'.\nThe default service is now 'test'.\n"
		assert config.get_values()["services"][0].name == "test"
		assert config.get_values()["services"][0].username == "testuser"
		assert config.get_values()["services"][0].password == "testpassword"
		assert config.get_values()["services"][0].url == "https://testhost:4447"
		# When no default service is set, the first service added is the default
		assert config.get_values()["service"] == "test"

		exit_code, stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test2", "--username=testuser", "--password=testpassword", "testhost2:443"]
		)
		assert exit_code == 0
		assert stdout == "Successfully added new service 'test2' with URL 'https://testhost2:443'.\nThe default service is now 'test'.\n"
		assert config.get_values()["services"][1].name == "test2"
		assert config.get_values()["services"][1].username == "testuser"
		assert config.get_values()["services"][1].password == "testpassword"
		assert config.get_values()["services"][1].url == "https://testhost2:443"
		# Default service is still the first one added
		assert config.get_values()["service"] == "test"

		exit_code, stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test2", "--username=testuser", "--password=testpassword", "--default", "testhost2:443"]
		)
		assert exit_code == 0
		assert stdout == "Successfully added new service 'test2' with URL 'https://testhost2:443'.\nThe default service is now 'test2'.\n"
		assert config.get_values()["services"][1].name == "test2"
		assert config.get_values()["services"][1].username == "testuser"
		assert config.get_values()["services"][1].password == "testpassword"
		assert config.get_values()["services"][1].url == "https://testhost2:443"
		# Default service is now test2
		assert config.get_values()["service"] == "test2"


def test_config_service_remove() -> None:
	config = Config()

	with temp_context() as tmp_path:
		# config service add writes conffile. Explicitely set here to avoid wiping config file of the user.
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile

		exit_code, _stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test", "--username=testuser", "--password=testpassword", "testhost"]
		)
		assert exit_code == 0
		exit_code, _stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test2", "--username=testuser", "--password=testpassword", "testhost2", "--default"]
		)
		assert exit_code == 0

		exit_code, stdout, _stderr = run_cli(["config", "service", "remove", "test"])
		assert exit_code == 0
		assert stdout == "Successfully removed service 'test'.\nThe default service is now 'test2'.\n"

		exit_code, stdout, _stderr = run_cli(["config", "service", "remove", "test2"])
		assert exit_code == 0
		assert stdout == "Successfully removed service 'test2'.\nThe default service is now unset.\n"


def test_config_service_set_default() -> None:
	config = Config()

	with temp_context() as tmp_path:
		# config service add writes conffile. Explicitely set here to avoid wiping config file of the user.
		# conffile = tmp_path / "conffile.conf"
		config.config_file_user = tmp_path / "config_file_user.conf"
		config.config_file_system = tmp_path / "config_file_system.conf"
		exit_code, _stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test", "--username=testuser", "--password=testpassword", "https://testurl:4447"]
		)
		exit_code, _stdout, _stderr = run_cli(
			["config", "service", "add", "--name=test2", "--username=testuser", "--password=testpassword", "https://testurl2:4447"]
		)

		exit_code, stdout, _stderr = run_cli(["config", "service", "set-default", "test2"])
		assert exit_code == 0
		assert stdout == "The default service is now 'test2'.\n"
		assert config.get_values().get("service") == "test2"
		config.read_config_files()
		assert config.get_values().get("service") == "test2"

		assert not config.config_file_system.exists()
		yaml = YAML().load(config.config_file_user.read_text())
		assert yaml["service"] == "test2"

		exit_code, stdout, _stderr = run_cli(["config", "service", "set-default", "test"])
		assert exit_code == 0
		assert stdout == "The default service is now 'test'.\n"
		assert config.get_values().get("service") == "test"
		config.read_config_files()
		assert config.get_values().get("service") == "test"

		exit_code, stdout, _stderr = run_cli(["config", "service", "set-default"])
		assert exit_code == 0
		assert stdout == "The default service is now unset.\n"
		assert config.get_values().get("service") is None
		config.read_config_files()
		assert config.get_values().get("service") is None

		exit_code, _stdout, _stderr = run_cli(["config", "service", "set-default", "nonexisting"])
		assert exit_code == 1
		assert config.get_values().get("service") is None
		config.read_config_files()
		assert config.get_values().get("service") is None


@pytest.mark.parametrize(
	"config_value, call_parameter",
	(("true", "--no-metadata"), ("false", "--metadata")),
)
def test_metadata_bool_flag(config_value: str, call_parameter: str) -> None:
	config = Config()

	with temp_context() as tmp_path:
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile
		exit_code, _stdout, _stderr = run_cli(["config", "set", "metadata", config_value])
		assert exit_code == 0
		exit_code, stdout, _stderr = run_cli(["--output-format=json", call_parameter, "config", "service", "list"])
		assert exit_code == 0
		print("config_value: ", config_value, "\ncall_parameter: ", call_parameter, "\noutput: ", stdout, "\n")
		assert (call_parameter == "--metadata") == ("metadata" in stdout)


@pytest.mark.parametrize(
	"config_value, call_parameter",
	(("false", "--header"), ("true", "--no-header")),
)
def test_header_bool_flag(config_value: str, call_parameter: str) -> None:
	config = Config()

	with temp_context() as tmp_path:
		conffile = tmp_path / "conffile.conf"
		config.config_file_user = conffile
		exit_code, _stdout, _stderr = run_cli(["config", "set", "header", config_value])
		assert exit_code == 0
		exit_code, stdout, _stderr = run_cli([call_parameter, "config", "service", "list"])
		assert exit_code == 0
		assert (call_parameter == "--header") == ("name" in stdout and "url" in stdout)


def test_list_attributes_flag() -> None:
	config = Config()
	try:
		exit_code, _stdout, _stderr = run_cli(["--list-attributes", "config", "list"])
		assert exit_code == 0
		exit_code, _stdout, _stderr = run_cli(["--list-attributes", "config", "service", "list"])
		assert exit_code == 0
	finally:
		config.list_attributes = False


@pytest.mark.parametrize(
	"cli_args, expect_error",
	[
		(["package", "control-to-toml", "dummyproduct"], True),
		(["--quiet", "package", "control-to-toml", "dummyproduct"], True),
		(["--quiet", "--hide-errors", "package", "control-to-toml", "dummyproduct"], False),
	],
)
def test_quiet_and_hide_errors_flags(cli_args: list, expect_error: bool) -> None:
	message = "Invalid value for '[SOURCE_DIR]': Directory 'dummyproduct' does not exist."
	_, _, _stderr = run_cli(cli_args)

	if expect_error:
		assert message in _stderr
	else:
		assert message not in _stderr


def test_quiet_and_hide_errors_flags_for_builtins_print() -> None:
	print("Prints to stdout unless --quiet is used", file=sys.stdout)
	print("Prints to stderr unless --hide-errors along with --quiet is used.", file=sys.stderr)

	_, _stdout, _stderr = run_cli(["--quiet", "package", "control-to-toml", "dummyproduct"])
	assert not _stdout
	assert _stderr

	_, _stdout, _stderr = run_cli(["--quiet", "--hide-errors", "package", "control-to-toml", "dummyproduct"])
	assert not _stdout
	assert not _stderr
