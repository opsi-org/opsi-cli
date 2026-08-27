import click
import pytest

from plugins.datastore.data.messages import _get_runtime_info


def test_get_runtime_info_edge_cases():
	# No click context
	with pytest.raises(RuntimeError, match="No Click context found"):
		_get_runtime_info()

	# No parent context
	parent_cmd = click.Command(name="client")
	parent_ctx = click.Context(parent_cmd)
	with parent_ctx, pytest.raises(RuntimeError, match="needs to be called within a Click sub-command"):
		_get_runtime_info()

	# wrong or incomplete context
	parent_cmd_unnamed = click.Command(name=None)
	parent_ctx_unnamed = click.Context(parent_cmd_unnamed)
	child_cmd_unnamed = click.Command(name="update")
	child_ctx_unnamed = click.Context(child_cmd_unnamed, parent=parent_ctx_unnamed)

	with child_ctx_unnamed, pytest.raises(ValueError, match="Incomplete context data found"):
		_get_runtime_info()
