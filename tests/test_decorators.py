# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_decorators
"""

import re

from .utils import run_cli


def clean_output(text: str) -> str:
	ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
	text = ansi_escape.sub("", text)
	text = re.sub(r"[^\x20-\x7E\s]", "", text)
	return " ".join(text.split())


def test_() -> None:
	"""
	# Test that the help output includes the dry-run support note for a dry-run capable command
	exit_code, stdout, stderr = run_cli(["--no-color", "self", "install", "--help"])
	combined_output = stdout + stderr
	combined_output = combined_output.replace("\n", "")
	assert "This command supports --dry-run: actions will be simulated and not performed." in combined_output
	"""
	# Test that a dry-run capable command shows a warning message when --dry-run is used
	exit_code, _stdout, stderr = run_cli(
		[
			"--dry-run",
			"self",
			"install",
		]
	)

	assert "WARNING: Operating in dry-run mode - no actions will be performed." in clean_output(stderr)

	# Test that a command not supporting dry-run shows an error message and aborts when --dry-run is used
	exit_code, _, stderr = run_cli(["--dry-run", "self", "command-structure"])
	assert "does not support --dry-run. Aborting." in clean_output(stderr)
