"""
test_config
"""

import sys
from io import BufferedReader, BytesIO, TextIOWrapper

import pytest

from opsicli.config import config
from opsicli.io import read_input, write_output
from tests.utils import run_cli

input_output_testdata = (
	(
		"json",
		'[{"somekey":"foo","someotherkey":"bar"},{"somekey":"bar"},{"someotherkey":"baz"},{}]',
		[{"somekey": "foo", "someotherkey": "bar"}, {"somekey": "bar"}, {"someotherkey": "baz"}, {}],
	),
	(
		"csv",
		"key1;key2;key3\r\nfirst1;first2;first3\r\nsecond1;second2;second3\r\n",
		[{"key1": "first1", "key2": "first2", "key3": "first3"}, {"key1": "second1", "key2": "second2", "key3": "second3"}],
	),
)


@pytest.mark.parametrize(("output_format", "string", "data"), input_output_testdata)
def test_output(output_format, string, data, capsys):
	old_output_format = config.output_format
	config.output_format = output_format
	write_output(data)
	config.output_format = old_output_format
	captured = capsys.readouterr()
	assert captured.out == string


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
def test_output_config(output_format, startstrings):
	exit_code, output = run_cli(["--output-format", output_format, "config", "list"])
	print(output)
	assert exit_code == 0
	assert any(output.startswith(startstring) for startstring in startstrings)
	print("\n\n")


@pytest.mark.parametrize(("input_format", "string", "data"), input_output_testdata)
def test_input(input_format, string, data):  # pylint: disable=unused-argument # format is automatically detected
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = read_input()
		sys.stdin = old_stdin
		assert result == data
