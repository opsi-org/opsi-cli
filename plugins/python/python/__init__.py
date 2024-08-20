"""
opsi-cli basic command line interface for opsi

python plugin
"""

import code
import sys
from pathlib import Path

import rich_click as click  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"


@click.command(short_help="Python interpreter")
@click.option("-V", "--version", is_flag=True, default=False, help="Print the Python version number and exit")
@click.option("-c", "command", metavar="cmd", required=False, help="Program passed in as string")
@click.argument("file", type=click.Path(file_okay=True, dir_okay=False, path_type=Path), required=False)
@click.argument("args", nargs=-1, type=str, required=False)
def python(version: bool, command: str, file: Path | None, args: list[str]) -> None:
	"""
	\b
	FILE : Program read from script file
	ARGS : Arguments passed to program in sys.argv[1:]
	"""
	if version:
		print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
		return

	if command:
		exec(command)
		return

	if file:
		sys.argv = [str(file)] + list(args)

		imp_new_module = type(sys)
		new_module = imp_new_module(str(file))
		new_module.__dict__["__name__"] = "__main__"
		new_module.__dict__["__file__"] = file

		exec(file.read_text(encoding="utf-8"), new_module.__dict__)
		return

	code.interact(local=locals())


class PythonPlugin(OPSICLIPlugin):
	name: str = "Python interpreter"
	description: str = "Run opsi-cli internal python interpreter"
	version: str = __version__
	cli = python
	flags: list[str] = ["protected"]
