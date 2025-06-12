# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_cli_helpers
"""

from .utils import run_cli


def test_help_shows_parent_options() -> None:
	exit_code, stdout, _ = run_cli(["client-action", "set-action-request", "--help"])
	assert exit_code == 0

	expected_order = [
		"Global options",
		"--log-level-stderr",
		"--color",
		"Client-action options",
		"--clients",
		"--client-groups",
		"Usage:",
		"Options",
	]

	positions = [stdout.find(text) for text in expected_order]
	assert all(pos != -1 for pos in positions)
	assert positions == sorted(positions)
