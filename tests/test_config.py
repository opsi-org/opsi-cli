"""
test_config
"""

from pathlib import Path
import pytest

from opsicli.types import LogLevel, Bool, OPSIServiceUrl, Password, Directory
from opsicli.config import ConfigItem, Config


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
def test_config_item_opsi_service_url(value, expected):
	item = ConfigItem(name="service_url", type=OPSIServiceUrl, value=value)
	assert item.value == expected


def test_config_item_password():
	item = ConfigItem(name="password", type=Password, value="password123")
	assert item.value == "password123"
	assert f"{item.value!r}" == "***secret***"


def test_config_item_plugin_dirs():
	item = ConfigItem(name="plugin_dirs", type=Directory, multiple=True, value=["/path1", "/path/2"])
	assert item.value == [Path("/path1"), Path("/path/2")]


def test_config_defaults():
	config = Config()
	assert config.color is True
	assert config.service_url == "https://localhost:4447"


def test_set_config():
	config = Config()
	assert config.color is True
	config.color = "false"
	assert config.color is False
	assert config.get_config_item("color").default is True
	assert config.get_config_item("color").value is False
