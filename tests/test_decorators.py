"""
test_decorators
"""

from unittest.mock import Mock, patch

import rich_click as click

from opsicli.decorators import handle_list_attributes
from opsicli.io import Attribute, Metadata


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
