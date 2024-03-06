"""
test_config
"""

import sys
from io import BufferedReader, BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any

import pytest
from _pytest.capture import CaptureFixture

from opsicli.config import config
from opsicli.io import (
	Attribute,
	Metadata,
	input_file_bin,
	input_file_str,
	output_file_bin,
	output_file_str,
	prompt,
	read_input,
	read_input_raw_bin,
	read_input_raw_str,
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
def test_output(output_format: str, string: str, data: Any, capsys: CaptureFixture[str]) -> None:
	old_output_format = config.get_values().get("output_format")
	config.set_values({"output_format": output_format})
	write_output(data)

	config.set_values({"output_format": old_output_format})
	captured = capsys.readouterr()
	assert captured.out == string


@pytest.mark.parametrize(
	"data,expected,sort_by",
	[
		(
			[{"a": "test_1", "b": "dummy", "c": "string"}, {"a": "test_2", "b": "aaaa", "c": "boolean"}],  # Test list[dict]
			'[{"a":"test_2","b":"aaaa","c":"boolean"},{"a":"test_1","b":"dummy","c":"string"}]',
			"b",
		),
		(
			[["test_1", "dummy", "string"], ["test_2", "aaaa", "boolean"]],  # Test list[list]
			'[["test_2","aaaa","boolean"],["test_1","dummy","string"]]',
			"value1",
		),
		(
			["test_1", "test_2"],  # Test list
			'["test_1","test_2"]',
			"value0",
		),
	],
)
def test_output_sort(capsys: CaptureFixture[str], data, expected, sort_by) -> None:
	old_config_values = config.get_values()
	try:
		config.set_values({"sort_by": sort_by, "output_format": "json"})
		write_output(data)
		captured = capsys.readouterr()
		assert captured.out.strip() == expected
	finally:
		config.set_values(old_config_values)


def test_output_sort_unsupported_data_type() -> None:
	old_config_values = config.get_values()
	try:
		data = {"a": "test_1", "b": "dummy", "c": "string"}
		config.set_values({"sort_by": "b", "output_format": "json"})
		with pytest.raises(RuntimeError):
			write_output(data)
	finally:
		config.set_values(old_config_values)


@pytest.mark.parametrize(
	"config_attributes, initial_order", [(["all"], ["c", "a", "b"]), (["b", "c", "a"], ["c", "a", "b"]), (["b", "c", "a"], ["a", "b", "c"])]
)
def test_attributes_ordering(config_attributes: list[str], initial_order: list[str]) -> None:
	data = [{"a": "testdata1_a", "b": "testdata1_b", "c": "testdata1_c"}, {"a": "testdata2_a", "b": "testdata2_b", "c": "testdata2_c"}]
	old_config_attribute = config.get_values().get("attributes")
	config.set_values({"attributes": config_attributes})
	metadata = Metadata(attributes=[Attribute(id=id) for id in initial_order])
	write_output(data, metadata)
	if config_attributes == ["all"]:
		assert [attr.id for attr in metadata.attributes] == initial_order
	else:
		assert [attr.id for attr in metadata.attributes] == config_attributes
	config.set_values({"attributes": old_config_attribute})


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
def test_output_config(output_format: str, startstrings: list[str]) -> None:
	exit_code, output = run_cli(["--output-format", output_format, "config", "list"])
	print(output)
	assert exit_code == 0
	assert any(output.startswith(startstring) for startstring in startstrings)
	print("\n\n")
	config.set_values({"output_format": "auto"})  # To not affect following tests


@pytest.mark.parametrize(("input_format", "string", "data"), input_output_testdata)
def test_input(input_format: str, string: str, data: Any) -> None:
	# with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:  # type: ignore[arg-type]
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = read_input()
		sys.stdin = old_stdin
		assert result == data


@pytest.mark.parametrize(
	("string", "input_type", "expected_result"), (("teststring", str, "teststring"), ("3.14159", float, 3.14159), ("42", int, 42))
)
def test_prompt(string: str, input_type: type, expected_result: str | float | int) -> None:
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:  # type: ignore[arg-type]
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = prompt("input some value", return_type=input_type)
		sys.stdin = old_stdin
		assert result == expected_result


@pytest.mark.parametrize("data", (b"binary", "string"))
def test_input_output_file(data: str | bytes) -> None:
	with temp_context() as tempdir:
		testfile = tempdir / "output.txt"
		config.output_file = testfile
		config.input_file = testfile
		if isinstance(data, bytes):
			with output_file_bin() as file:
				file.write(data)
			with input_file_bin() as file:
				assert file.read() == data
		else:
			with output_file_str() as file:
				file.write(data)
			with input_file_str() as file:
				assert file.read() == data


@pytest.mark.parametrize("data", (b"binary", "string"))
def test_input_output_file_raw(data: str | bytes) -> None:
	with temp_context() as tempdir:
		testfile = tempdir / "output.txt"
		config.output_file = testfile
		config.input_file = testfile
		write_output_raw(data)
		if isinstance(data, bytes):
			assert read_input_raw_bin() == data
		else:
			assert read_input_raw_str() == data


def test_input_output_file_cli() -> None:
	with temp_context() as tempdir:
		for outputfile in (tempdir / "output.txt", Path("relative-output.txt")):
			try:
				exit_code, _ = run_cli([f"--output-file={outputfile}", "config", "list"])
				assert exit_code == 0
				assert "log_level" in outputfile.read_text(encoding="utf-8")
			finally:
				outputfile.unlink()

		# --input-file is only used in jsonrpc plugin which requires a server connection
