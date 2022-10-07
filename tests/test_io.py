"""
test_config
"""

import sys
from io import BufferedReader, BytesIO, TextIOWrapper

import pytest

from opsicli.io import read_input
from tests.utils import run_cli


# msgpack output is not encoded to be read in terminal -> not tested here!
@pytest.mark.parametrize(
	("output_format", "startstrings"),
	(
		("auto", ["╭────", "\u250c\u2500\u2500\u2500\u2500"]),
		("json", ['[{"name":']),
		("pretty-json", ['[\n  {\n    "name":']),
		("table", ["╭────", "\u250c\u2500\u2500\u2500\u2500"]),
		("csv", ["name;"]),
	),
)
def test_output(output_format, startstrings):
	exit_code, output = run_cli(["--output-format", output_format, "config", "list"])
	print(output)
	assert exit_code == 0
	assert any(output.startswith(startstring) for startstring in startstrings)
	print("\n\n")


@pytest.mark.parametrize(
	("string", "data"),
	(
		('{"something":{"another":[1,2,3]}}', {"something": {"another": [1, 2, 3]}}),
		(
			"key1;key2;key3\nfirst1;first2;first3\nsecond1;second2;second3",
			[{"key1": "first1", "key2": "first2", "key3": "first3"}, {"key1": "second1", "key2": "second2", "key3": "second3"}],
		),
	),
)
def test_input2(string, data):
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = read_input()
		sys.stdin = old_stdin
		assert result == data
