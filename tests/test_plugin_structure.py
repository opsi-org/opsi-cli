# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import importlib.util
from pathlib import Path

import pytest
from opsicommon.logging import get_logger

from opsicli.cli_helpers import _get_opsi_commands_and_functions

test_plugins_dir = Path("./tests/test_data/false_structure_plugins")
functions = _get_opsi_commands_and_functions()

logger = get_logger("opsi-cli")


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
		data_path = plugin_path / "data"
		metadata_path = plugin_path / "python" / "metadata.py"
		init_path = plugin_path / "python" / "__init__.py"

		data_dir = list(plugin_path.rglob("data"))
		metadata_file = list(plugin_path.rglob("metadata.py"))
		init_file = list(plugin_path.rglob("__init__.py"))
		all_files = list(plugin_path.rglob("*.py"))
		leftover_files = list(set(metadata_file) ^ set(init_file) ^ set(all_files))

		# if data_dir: right path?
		if data_dir:
			if not data_path.exists():
				errors.append(f"{plugin_name}: \n - data directory should be at '{data_path}'.")

		# if metadata.py: right path?
		if metadata_file:
			if not metadata_path.exists():
				errors.append(
					f"{plugin_name}: \n - metadata.py should be at '{metadata_path}' and named after corrsesponding command sequence. (e.g. 'datastore_config-state_list')"
				)

		# if __init__.py: right path?
		if init_file:
			if not init_path.exists():
				errors.append(f"{plugin_name}: \n - __init__.py should be at '{init_path}'.")
			else:
				# search for metadata in __init__.py
				content = init_path.read_text()
				if "Metadata(" in content:
					errors.append(
						f"{plugin_name}: \n - metadata should be in '{metadata_path}', not in '{init_path}' and named after corrsesponding command sequence. (e.g. 'datastore_config-state_list')"
					)
		# __init__ does not exist
		else:
			errors.append(f"{plugin_name}: \n - missing __init__.py. It should be at '{init_path}'.")

		if leftover_files:
			for file in leftover_files:
				# search for metadata in every other file
				content = file.read_text()
				if "Metadata(" in content:
					errors.append(
						f"{plugin_name}: \n - metadata should be in '{metadata_path}', not in '{file}' and named after corrsesponding command sequence. (e.g. 'datastore_config-state_list')"
					)

	# only return, if testing with test plugins
	if test_plugins_dir:
		return "\n\n" + "\n--- Invalid plugin directory structure ---\n" + "\n".join(errors) + "\n\n"
	assert not errors, "\n\n" + "\n--- Invalid plugin directory structure ---\n" + "\n".join(errors) + "\n\n"


@pytest.mark.opsi_service
def test_metadata_naming() -> None:
	plugins_dir = Path("./plugins")
	for plugin in plugins_dir.iterdir():
		metadata_path = plugin / "python" / "metadata.py"

		# does metadata.py exist?
		if not metadata_path.exists():
			continue
		spec = importlib.util.spec_from_file_location(plugin.name, metadata_path)
		if spec is None or spec.loader is None:
			raise ImportError(f"Could not load spec for {Path(f'./plugins/{plugin}/data/metadata.py').resolve()}")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)

		# get metadata names
		if hasattr(module, "COMMAND_METADATA"):
			data = getattr(module, "COMMAND_METADATA")
			metadata_keys = data.keys()
			functions_keys = functions.keys()

		# test if there is a corresponding function with same command sequence as key
		# metadata name should be command sequence name
		# e.g. 'datastore config-state list' => 'datastore_config-state_list'
		# IMPORTANT for --list-attributes to work
		for key in metadata_keys:
			if key not in functions_keys:
				assert False, (
					f"False metadata naming: '{key}'. Metadata should be named after corresponding command sequence. (e.g. 'datastore config-state list' => 'datastore_config-state_list')"
				)


@pytest.mark.opsi_service
def test_plugin_structure_test() -> None:
	raw_errors = test_plugin_structure(test_plugins_dir) or ""
	errors = raw_errors.replace("\n", "")
	assert "Invalid plugin directory structure" in errors
	# false_init
	assert "false_init:  - __init__.py should be at" in errors
	# false_metadata_and_missing_init
	assert "false_metadata_and_missing_init:  - metadata.py should be at" in errors
	assert "false_metadata_and_missing_init:  - missing __init__.py. It should be at" in errors
	# false_named_init
	assert "false_named_init:  - missing __init__.py. It should be at" in errors
	# false_data
	assert "false_data:  - data directory should be at" in errors
	# misplaced metadata
	assert "misplaced_metadata:  - metadata should be in" in errors
