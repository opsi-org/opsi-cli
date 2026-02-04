import importlib
from pathlib import Path

import pytest

from opsicli.cli_helpers import _get_opsi_commands_and_functions

plugins_dir = Path("./plugins")
functions = _get_opsi_commands_and_functions()


@pytest.mark.opsi_service
def test_plugin_structure() -> None:
	errors = []

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

	assert not errors, "\n--- Invalid plugin directory structure ---\n" + "\n".join(errors)


@pytest.mark.opsi_service
def test_metadata_naming() -> None:
	for plugin_folder in plugins_dir.iterdir():
		metadata_path = plugin_folder / "data" / "metadata.py"

		# does metadata.py exist?
		if not metadata_path.exists():
			continue
		spec = importlib.util.spec_from_file_location(plugin_folder.name, metadata_path)
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

def test_plguin_structure_test() -> None:
