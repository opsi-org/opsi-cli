import importlib
from pathlib import Path

from opsicli.cli_helpers import _get_opsi_command_functions
from opsicli.io import console_print

# Pfad zum Plugins-Ordner (basierend auf deinen Screenshots)
plugins_dir = Path("./plugins")
functions = _get_opsi_command_functions()


def test_plugin_structure():
	errors = []

	for plugin_path in plugins_dir.iterdir():
		plugin_name = plugin_path.name
		data_folder = plugin_path / "data"
		metadata_file = plugin_path / "data" / "metadata.py"
		python_init = plugin_path / "python" / "__init__.py"

		if not data_folder.exists():
			errors.append(f"Plugin {plugin_name}: Missing folder: {data_folder}")

		if not python_init.exists():
			errors.append(f"Plugin{plugin_name}: Missing folder {python_init}")

		# search for Metadata in __init__
		content = python_init.read_text()
		if "Metadata(" in content:
			errors.append(
				f"Plugin {plugin_name}: Metadata should be in '{data_folder}/metadata.py' and [red]named [/red]after corrsesponding command sequence. [red]e.g 'datastore_config-state_list'[/red]"
			)

	if errors:
		console_print("\n--- Invalid plugin directory structure ---")
		for error in errors:
			console_print(f"[!] {error}")
		assert False
	else:
		console_print(f"All {len([p for p in plugins_dir.iterdir() if p.is_dir()])} Plugins are configured correctly.")
		assert True


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

		# test if there is a corresponding function with same command sequence
		# metadata name should be command sequence name
		# IMPORTANT for --list-attributes to work
		for key in metadata_keys:
			if key not in functions_keys:
				assert False, f"'{key}': Metadata should be named after corresponding command sequence."
