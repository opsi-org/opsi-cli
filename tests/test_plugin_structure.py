import importlib.util
from pathlib import Path

import pytest

from opsicli.cli_helpers import _get_opsi_commands_and_functions

test_plugins_dir = Path("./tests/test_data/false_structure_plugins")
functions = _get_opsi_commands_and_functions()


@pytest.mark.opsi_service
def test_plugin_structure(test_plugins_dir: Path | None = None) -> str | None:
	errors = []

	# for testing this test
	if test_plugins_dir:
		plugins_dir = Path(test_plugins_dir)
	else:
		plugins_dir = Path("./plugins")

	for plugin_path in plugins_dir.iterdir():
		plugin_name = plugin_path.name
		metadata_file_path = plugin_path / "data" / "metadata.py"
		python_init_path = plugin_path / "python" / "__init__.py"

		metadata_file = list(plugin_path.rglob("metadata.py"))

		# if metadata.py: right path?
		if metadata_file:
			if not metadata_file_path.exists():
				errors.append(
					f"Plugin {plugin_name}: Metadata should be in '{metadata_file_path}' and [red]named [/red]after corrsesponding command sequence. [red]e.g. 'datastore_config-state_list'[/red]"
				)

		if not python_init_path.exists():
			errors.append(f"For plugin {plugin_name}: Missing init file – '{python_init_path}'")
		else:
			# search for Metadata in __init__
			content = python_init_path.read_text()
			if "Metadata(" in content:
				errors.append(
					f"Plugin {plugin_name}: Metadata should be in '{metadata_file_path}' and [red]named [/red]after corrsesponding command sequence. [red]e.g. 'datastore_config-state_list'[/red]"
				)
	if test_plugins_dir:
		return "\n--- Invalid plugin directory structure ---\n" + "\n".join(errors)
	assert not errors, "\n--- Invalid plugin directory structure ---\n" + "\n".join(errors)


@pytest.mark.opsi_service
def test_metadata_naming() -> None:
	plugins_dir = Path("./plugins")
	for plugin in plugins_dir.iterdir():
		metadata_path = plugin / "data" / "metadata.py"

		# does metadata.py exist?
		if not metadata_path.exists():
			continue
		spec = importlib.util.spec_from_file_location(plugin.name, metadata_path)
		if spec is None or spec.loader is None:
			raise ImportError(f"Could not load spec for {Path(f'./plugins/{plugin}/data/metadata.py').resolve()}")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)

		# get metadata names
		if hasattr(module, "command_metadata"):
			data = getattr(module, "command_metadata")
			metadata_keys = data.keys()
			functions_keys = functions.keys()
		# test if there is a corresponding function with same command sequence as key
		# metadata name should be command sequence name
		# IMPORTANT for --list-attributes to work
		for key in metadata_keys:
			if key not in functions_keys:
				assert False, f"'{key}': Metadata should be named after corresponding command sequence."


@pytest.mark.opsi_service
def test_plugin_structure_test() -> None:
	raw_errors = test_plugin_structure(test_plugins_dir)
	assert raw_errors
	errors = raw_errors.replace("\n", "")
	assert "Invalid plugin directory structure" in errors
	assert "For plugin false_init: Missing init file" in errors
	assert "For plugin false_metadata_and_missing_init: Missing init file" in errors
	assert "Plugin false_metadata_and_missing_init: Metadata should be in" in errors
	assert "Plugin false_metadata_dir: Metadata should be in" in errors
	assert "For plugin false_named_init: Missing init file" in errors
