# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_decorators
"""

from unittest.mock import Mock, patch

import rich_click as click

from opsicli.decorators import handle_list_attributes
from opsicli.io import Attribute, Metadata

from .utils import run_cli


def test_handle_list_attributes() -> None:
	mock_config = Mock()
	mock_config.list_attributes = True

	mock_module = Mock()

	ctx = Mock()
	ctx.command = Mock(spec=click.Group)
	ctx.invoked_subcommand = "list"
	ctx.command_path = "command subcommand"

	with patch("opsicli.decorators.config", mock_config), patch("opsicli.decorators.importlib.import_module", return_value=mock_module):
		metadata = Metadata(
			attributes=[
				Attribute(id="name", identifier=True, data_type="str"),
				Attribute(id="type", data_type="str"),
			]
		)
		mock_module.command_metadata = {"subcommand_list": metadata}

		@handle_list_attributes
		def test_func(ctx: click.Context) -> str:
			return "Test function executed"

		result = test_func(ctx)
		ctx.exit.assert_called_once()
		assert result == "Test function executed"


def test_dry_run_handling() -> None:
	# Test that the help output includes the dry-run support note for a dry-run capable command
	exit_code, stdout, stderr = run_cli(["--no-color", "self", "install", "--help"])
	combined_output = stdout + stderr
	assert "This command supports --dry-run: actions will be simulated and not performed." in combined_output

	# Test that a dry-run capable command shows a warning message when --dry-run is used
	exit_code, _, stderr = run_cli(
		[
			"--dry-run",
			"self",
			"install",
		]
	)
	stderr = " ".join(stderr.split())
	assert "WARNING: Operating in dry-run mode - no actions will be performed." in stderr

	# Test that a command not supporting dry-run shows an error message and aborts when --dry-run is used
	exit_code, _, stderr = run_cli(["--dry-run", "self", "command-structure"])
	stderr = " ".join(stderr.split())
	assert "does not support --dry-run. Aborting." in stderr
