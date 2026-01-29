import importlib
import inspect
import re
import sys
from pathlib import Path

import pytest

from opsicli.cli_helpers import _get_opsi_command_functions
from opsicli.io import list_attributes
from tests.utils import run_cli


def clean_output(text: str) -> str:
	ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
	text = ansi_escape.sub("", text)
	text = re.sub(r"[^\x20-\x7E\s]", "", text)
	return " ".join(text.split())


@pytest.mark.opsi_service
def test_list_attributes_flag(capsys) -> None:
	path = Path("./plugins")
	plugins = [f.name for f in path.iterdir() if f.is_dir]
	for p in plugins:
		# check for metadata.py
		module_path = Path(f"./plugins/{p}/data/metadata.py").resolve()
		if module_path.exists():
			# load module dynamically
			spec = importlib.util.spec_from_file_location(p, module_path)
			plugin_metadata_module = importlib.util.module_from_spec(spec)
			sys.modules[p] = plugin_metadata_module
			spec.loader.exec_module(plugin_metadata_module)

			# sequences used as key for metadata  	e.g. ['datastore_config-state_list', 'jsonrpc_methods']
			metadata_keys = list(plugin_metadata_module.command_metadata.keys())
			# sequences used for cli 				e.g. [['datastore', 'config-state', 'list'], ['jsonrpc', 'methods']]
			command_sequences_cli = [cs.replace("_", " ").split(" ") for cs in metadata_keys]

			for metadata_key, sequence_cli in zip(metadata_keys, command_sequences_cli):
				plugin_metadata = plugin_metadata_module.command_metadata[metadata_key]

				# expected output
				list_attributes(plugin_metadata)
				expected_output = capsys.readouterr()

				# opsi-cli output
				exit_code, _stdout, _stderr = run_cli(["--list-attributes"] + sequence_cli)
				assert exit_code == 0
				assert _stdout == expected_output.out


@pytest.mark.opsi_service
def test_dry_run_capability(capsys) -> None:
	functions = _get_opsi_command_functions()

	for path, func in functions.items():
		source = inspect.getsource(func)
		exit_code, stdout, stderr = run_cli(["--dry-run", "--no-color"] + path.split())

		captured = capsys.readouterr()
		combined_output = (captured.out + captured.err).replace("\n", " ")
		print(combined_output)
		if "@dry_run_capable" in source:
			assert "WARNING: Operating in dry-run mode" in combined_output
		else:
			assert "does not support --dry-run. Aborting." in combined_output
