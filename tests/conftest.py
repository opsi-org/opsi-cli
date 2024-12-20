# -*- coding: utf-8 -*-

# opsiclientd is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2010-2021 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0
"""
This file is part of opsi - https://www.opsi.org
"""

import builtins
import os
import platform
from typing import Any

import pytest
import requests  # type: ignore[import]
from _pytest.logging import LogCaptureHandler
from _pytest.nodes import Item

from opsicli.config import config
from opsicli.opsiservice import get_service_connection

from . import OPSI_HOSTNAME

builtins_print = builtins.print


def emit(*args: Any, **kwargs: Any) -> None:
	pass


LogCaptureHandler.emit = emit  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def clear_service_client_cache() -> None:
	get_service_connection.cache_clear()


@pytest.fixture(autouse=True)
def reset_config() -> None:
	for item in config.get_config_items():
		item.set_value(item.default)
	builtins.print = builtins_print


def running_in_docker() -> bool:
	return os.path.exists("/.dockerenv")


def admin_permissions() -> bool:
	try:
		return os.geteuid() == 0
	except AttributeError:
		import ctypes

		return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]


def testcontainer_running() -> bool:
	try:
		result = requests.get(f"https://{OPSI_HOSTNAME}:4447/public", timeout=5, verify=False)
		return result.status_code == 200
	except requests.exceptions.ConnectionError:
		return False


PLATFORM = platform.system().lower()
RUNNING_IN_DOCKER = running_in_docker()
ADMIN_PERMISSIONS = admin_permissions()
TESTCONTAINER_RUNNING = testcontainer_running()


def pytest_runtest_setup(item: Item) -> None:
	supported_platforms = []
	for marker in item.iter_markers():
		if marker.name == "docker_linux" and not RUNNING_IN_DOCKER:
			pytest.skip("Must run in docker")
			return
		if marker.name == "not_in_docker" and RUNNING_IN_DOCKER:
			pytest.skip("Cannot run in docker")
			return
		if marker.name == "admin_permissions" and not ADMIN_PERMISSIONS:
			pytest.skip("No admin permissions")
			return
		if marker.name == "requires_testcontainer" and not TESTCONTAINER_RUNNING:
			pytest.skip("Cannot run without testcontainer")
			return
		if marker.name in ("windows", "linux", "darwin", "posix"):
			if marker.name == "posix":
				supported_platforms.extend(["linux", "darwin"])
			else:
				supported_platforms.append(marker.name)

	if supported_platforms and PLATFORM not in supported_platforms:
		pytest.skip(f"Cannot run on {PLATFORM}")
