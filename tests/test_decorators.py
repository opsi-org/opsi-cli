# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_decorators
"""

import pytest

from .utils import assert_error_contains, run_cli


def test_dry_run_support_note() -> None:
	# Test that the help output includes the dry-run support note for a dry-run capable command
	exit_code, stdout, _stderr = run_cli(["--no-color", "self", "install", "--help"])
	assert "This command supports --dry-run: actions will be simulated" in stdout.replace("\n", " ").replace("  ", " ")


@pytest.mark.parametrize("command", ("client", "config-state", "product-client-state", "product-property-state"))
def test_mutually_exclusive(command: str) -> None:
	exit_code, stdout, _stderr = run_cli(["datastore", command, "list", "--where", "objectId=j*", "--all"])
	assert exit_code != 0
	assert_error_contains(_stderr, ("The options", "--where", "--all", "are mutually", "exclusive"))
