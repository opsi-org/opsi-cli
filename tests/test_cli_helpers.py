# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_cli_helpers
"""

from .utils import run_cli


def test_help_command_hierarchy_for_group() -> None:
	exit_code, stdout, _ = run_cli(["config", "service", "list", "--help"])
	assert exit_code == 0

	hierarchy = stdout.split("Command Hierarchy")[-1]
	expected = [
		"opsi-cli  opsi command line interface",
		"└── config  Manage opsi-cli configuration",
		"    └── service  Configuration of opsi services",
		"        └── list  List configured opsi services",
	]
	for line in expected:
		assert line in hierarchy


def test_help_command_hierarchy_for_command() -> None:
	exit_code, stdout, _ = run_cli(["terminal", "--help"])
	assert exit_code == 0
	hierarchy = stdout.split("Command Hierarchy")[-1]
	expected = [
		"opsi-cli  opsi command line interface",
		"└── terminal  Start remote terminal session",
	]
	for line in expected:
		assert line in hierarchy
