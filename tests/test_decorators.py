# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_decorators
"""

from .utils import run_cli


def test_() -> None:
	# Test that the help output includes the dry-run support note for a dry-run capable command
	exit_code, stdout, stderr = run_cli(["--no-color", "self", "install", "--help"])
	combined_output = stdout + stderr
	combined_output = combined_output.replace("\n", "")
	assert "This command supports --dry-run: actions will be simulated" in combined_output
