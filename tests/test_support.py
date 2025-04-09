# -*- coding: utf-8 -*-

# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_support
"""

import pytest

from .utils import run_cli


@pytest.mark.opsi_service
def test_healthcheck() -> None:
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check"])
	print(stdout)
	print(_stderr)
	assert exit_code == 0
	keywords = ("opsiconfd_config", "disk_usage", "redis", "mysql")
	for word in keywords:
		assert word in stdout


@pytest.mark.opsi_service
def test_healthcheck_detailed() -> None:
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "--detailed"])
	assert exit_code == 0
	assert "No problems detected" in stdout
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "mysql"])
	assert exit_code == 0
	assert "No MySQL issues found." in stdout
