# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_cli_helpers
"""

import pytest

from .utils import run_cli


@pytest.mark.parametrize("color", (True, False))
def test_help_shows_parent_options(color: bool) -> None:
	exit_code, stdout, _ = run_cli((["--color"] if color else ["--no-color"]) + ["client-action", "set-action-request", "--help"])
	assert exit_code == 0

	expected_order = [
		"GLOBAL OPTIONS",
		"--log-level-stderr",
		"--color",
		"CLIENT-ACTION OPTIONS",
		"--clients",
		"--client-groups",
		"SET-ACTION-REQUEST OPTIONS",
		"--where-failed",
		"--process",
		"Usage:",
	]

	positions = [stdout.find(text) for text in expected_order]

	assert all(pos != -1 for pos in positions)
	assert positions == sorted(positions)


def test_usage_help_contains_option_placeholders() -> None:
	exit_code, stdout, _ = run_cli(["config", "service", "list", "--help"])
	assert exit_code == 0
	assert "[GLOBAL OPTIONS]" in stdout
	assert "[CONFIG OPTIONS]" in stdout
	assert "[SERVICE OPTIONS]" in stdout
