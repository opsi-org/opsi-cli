"""
test_config
"""

from pathlib import Path

import pytest

from opsicli.config import Config, ConfigItem
from opsicli.types import Bool, Directory, LogLevel, OPSIServiceUrl, Password

from .utils import run_cli, temp_context


@pytest.mark.parametrize(
	"default, value, expected",
	((None, None, None), ("1", None, 1), (1, 10, 10), (None, 1, 1)),
)
def test_config_item_defaults(default, value, expected):
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
def test_config_item_log_level(value, expected, exception):
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
def test_config_item_bool(value, expected):
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
def test_config_item_opsi_service(value, expected):
	item = ConfigItem(name="service", type=OPSIServiceUrl, value=value)
	# as_dict produces Dict containing Dict of values being Dicts with the actual value
	assert item.as_dict()["value"].get("value") == expected
	assert item.value == expected


def test_config_item_password():
	item = ConfigItem(name="password", type=Password, value="password123")
	assert item.value == "password123"
	assert f"{item.value!r}" == "***secret***"


@pytest.mark.posix
def test_config_item_plugin_user_dir_posix():
	item = ConfigItem(name="plugin_user_dir", type=Directory, value="/path1")
	assert item.value == Path("/path1")


@pytest.mark.windows
def test_config_item_plugin_user_dir_windows():
	item = ConfigItem(name="plugin_user_dir", type=Directory, value=r"C:\path1")
	assert item.value == Path(r"C:\path1")


def test_config_defaults():
	config = Config()
	assert config.color is True
	assert config.service == "https://localhost:4447"


def test_set_config():
	config = Config()
	assert config.color is True
	config.color = "false"
	assert config.color is False
	assert config.get_config_item("color").default is True
	assert config.get_config_item("color").value is False


def test_read_write_config():
	config = Config()
	with temp_context() as tempdir:
		conffile = Path(tempdir) / "conffile.conf"
		config.config_file_user = conffile
		# Write any config value and save
		exit_code, output = run_cli(["config", "set", "output_format", "csv"])
		print(output)
		assert exit_code == 0
		assert conffile.exists()
		config.set_values({"output_format": "msgpack"})
		# Load config from file and check if value is set
		config.read_config_files()
		print(config.get_values().get("output_format"))
		assert config.get_values().get("output_format") == "csv"
		assert config.output_format == "csv"
		exit_code, _ = run_cli(["config", "unset", "output_format"])
		assert exit_code == 0
		assert config.get_values().get("output_format") == "auto"


def test_service_config():
	config = Config()
	(exit_code, _) = run_cli(
		["config", "service", "add", "--name=test", "--username=testuser", "--password=testpassword", "https://testurl:4447"]
	)
	assert exit_code == 0
	assert any(service.name == "test" for service in config.get_values().get("services", []))
	(exit_code, _) = run_cli(["config", "service", "remove", "test"])
	assert exit_code == 0
	assert not any(service.name == "test" for service in config.get_values().get("services", []))
