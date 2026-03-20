# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_plugin_python
"""

import sys
from pathlib import Path

from .utils import run_cli


def test_python_version() -> None:
	exit_code, stdout, _stderr = run_cli(["python", "--version"])
	assert exit_code == 0
	assert stdout == f"Python {sys.version.split()[0]}\n"


def test_python_cmd() -> None:
	exit_code, stdout, stderr = run_cli(
		[
			"python",
			"-c",
			"import sys; sys.stdout.write('stdout'); sys.stderr.write('stderr'); sys.stdout.flush(); sys.stderr.flush(); sys.exit(10);",
		]
	)
	assert exit_code == 10
	assert stdout == "stdout"
	assert stderr == "stderr"


def test_python_script(tmp_path: Path) -> None:
	script = tmp_path / "script.py"
	script.write_text("import sys\nfrom opsicli.io import console_print\nconsole_print(','.join(sys.argv))\nsys.exit(3)\n")
	exit_code, _stdout, stderr = run_cli(["python", str(script), "arg1", "arg2", "--option", "value"])
	assert exit_code == 3
	assert stderr.replace("\n", "").strip() == f"{script},arg1,arg2,--option,value"
