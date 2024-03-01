# -*- coding: utf-8 -*-

# opsiclientd is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2010-2021 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0
"""
This file is part of opsi - https://www.opsi.org
"""

import os
import platform
import warnings
from typing import Any

import pytest
import requests  # type: ignore[import]
import urllib3  # type: ignore[import]
from _pytest.config import Config as PytestConfig
from _pytest.logging import LogCaptureHandler
from _pytest.nodes import Item

from . import OPSI_HOSTNAME


def emit(*args: Any, **kwargs: Any) -> None:
	pass


LogCaptureHandler.emit = emit  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def disable_insecure_request_warning() -> None:
	warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)


@pytest.hookimpl()
def pytest_configure(config: PytestConfig) -> None:
	# https://pypi.org/project/pytest-asyncio
	# When the mode is auto, all discovered async tests are considered
	# asyncio-driven even if they have no @pytest.mark.asyncio marker.
	config.option.asyncio_mode = "auto"
	# register custom markers
	config.addinivalue_line("markers", "docker_linux: mark test to run only on linux in docker")
	config.addinivalue_line("markers", "not_in_docker: mark test to run only if not running in docker")
	config.addinivalue_line("markers", "admin_permissions: mark test to run only if user has admin permissions")
	config.addinivalue_line("markers", "windows: mark test to run only on windows")
	config.addinivalue_line("markers", "linux: mark test to run only on linux")
	config.addinivalue_line("markers", "darwin: mark test to run only on darwin")
	config.addinivalue_line("markers", "posix: mark test to run only on posix")


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
