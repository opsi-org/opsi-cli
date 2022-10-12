"""
test_config
"""

import sys
from io import BufferedReader, BytesIO, TextIOWrapper

import pytest

from opsicli.config import config
from opsicli.io import (
	input_file,
	output_file,
	prompt,
	read_input,
	read_input_raw,
	write_output,
	write_output_raw,
)
from tests.utils import run_cli, temp_context

input_output_testdata = (
	(
		"json",
		'{"somekey":"foo","someotherkey":"bar","somethirdkey":"baz"}',
		{"somekey": "foo", "someotherkey": "bar", "somethirdkey": "baz"},
	),
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


@pytest.mark.parametrize(
	("string", "input_type", "expected_result"), (("teststring", str, "teststring"), ("3.14159", float, 3.14159), ("42", int, 42))
)
def test_prompt(string, input_type, expected_result):
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = prompt("input some value", return_type=input_type)
		sys.stdin = old_stdin
		assert result == expected_result


@pytest.mark.parametrize("encoding", ("utf-8", "binary"))
def test_input_output_file(encoding):
	teststring = "teststring"
	with temp_context() as tempdir:
		testfile = tempdir / "output.txt"
		config.output_file = testfile
		config.input_file = testfile
		with output_file(encoding=encoding) as file_handle:
			if encoding == "binary":
				file_handle.write(teststring.encode("utf-8"))
			else:
				file_handle.write(teststring)
		with input_file(encoding=encoding) as file_handle:
			result = file_handle.read()
			if encoding == "binary":
				assert result == teststring.encode("utf-8")
			else:
				assert result == teststring


@pytest.mark.parametrize("encoding", ("utf-8", "binary"))
def test_input_output_file_raw(encoding):
	teststring = "teststring"
	with temp_context() as tempdir:
		testfile = tempdir / "output.txt"
		config.output_file = testfile
		config.input_file = testfile
		if encoding == "binary":
			write_output_raw(teststring.encode("utf-8"))
		else:
			write_output_raw(teststring)
		if encoding == "binary":
			assert read_input_raw(encoding=encoding) == teststring.encode("utf-8")
		else:
			assert read_input_raw() == teststring
