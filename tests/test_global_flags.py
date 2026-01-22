import importlib
import sys
from pathlib import Path

from opsicli.io import list_attributes
from tests.utils import run_cli

# from opsicli.io import list_attributes


def test_list_attributes_flag(capsys) -> None:
	path = Path("./plugins")
	plugins = [f.name for f in path.iterdir() if f.is_dir()]

	for p in plugins:
		# check for metadata.py
		if Path(f"./plugins/{p}/data/metadata.py").exists():
			# build module_path
			module_path = Path(f"./plugins/{p}/data/metadata.py").resolve()

			# load module dynamically
			spec = importlib.util.spec_from_file_location(p, module_path)
			plugin_metadata_module = importlib.util.module_from_spec(spec)
			sys.modules[p] = plugin_metadata_module
			spec.loader.exec_module(plugin_metadata_module)

			# sequences used as key for metadata  	e.g. ['datastore_config-state_list', 'jsonrpc_methods']
			command_sequences_metadata = list(plugin_metadata_module.command_metadata.keys())
			# sequences used for cli 				e.g. [['datastore', 'config-state', 'list'], ['jsonrpc', 'methods']]
			command_sequences_cli = [cs.replace("_", " ").split(" ") for cs in command_sequences_metadata]

			for sequence_metadata, sequence_cli in zip(command_sequences_metadata, command_sequences_cli):
				plugin_metadata = plugin_metadata_module.command_metadata[sequence_metadata]

				# expected
				list_attributes(plugin_metadata)
				expected_output = capsys.readouterr()

				# test cli
				exit_code, _stdout, _stderr = run_cli(["--list-attributes"] + sequence_cli)
				assert exit_code == 0
				assert _stdout == expected_output.out
