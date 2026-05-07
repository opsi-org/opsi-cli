# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_config
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from io import BufferedReader, BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from typing import Any
from unittest.mock import patch

import orjson
import pytest
from _pytest.capture import CaptureFixture
from opsi.logging import use_logging_config

from opsicli.config import config
from opsicli.io import (
	Attribute,
	Metadata,
	OutputType,
	console_print,
	deprecation_warning,
	get_console,
	get_selected_attributes,
	get_selected_timezone,
	get_separated_entries,
	input_file_bin,
	input_file_str,
	list_attributes,
	output_file_bin,
	output_file_str,
	prompt,
	read_input,
	read_input_raw_bin,
	read_input_raw_str,
	to_string,
	write_output,
	write_output_raw,
	write_output_table,
)
from tests.utils import run_cli, temp_context

from .conftest import PLATFORM


@pytest.mark.parametrize(
	"output_type, expected_auto_file",
	(
		(OutputType.ERROR_MESSAGE, "stderr"),
		(OutputType.MESSAGE, "stderr"),
		(OutputType.WARNING_MESSAGE, "stderr"),
		(OutputType.PROGRESS, "stderr"),
		(OutputType.DATA, "stdout"),
		(OutputType.PROMPT, "stderr"),
	),
)
def test_get_console(capsys: CaptureFixture[str], output_type: OutputType, expected_auto_file: str) -> None:
	for file in None, sys.stdout, sys.stderr:
		for quiet in True, False:
			for hide_errors in True, False:
				config.set_values({"quiet": quiet, "hide_errors": hide_errors})

				console = get_console(output_type=output_type, file=file)
				console.print("test")
				captured = capsys.readouterr()

				expect_out = "test\n"
				if quiet and output_type not in (OutputType.ERROR_MESSAGE, OutputType.WARNING_MESSAGE, OutputType.PROMPT, OutputType.DATA):
					expect_out = ""
				if hide_errors and output_type in (OutputType.ERROR_MESSAGE, OutputType.WARNING_MESSAGE):
					expect_out = ""

				if file == sys.stdout or (not file and expected_auto_file == "stdout"):
					assert captured.out == expect_out
					assert captured.err == ""

				elif file == sys.stderr or (not file and expected_auto_file == "stderr"):
					assert captured.out == ""
					assert captured.err == expect_out

				else:
					raise RuntimeError("Invalid file type")


@pytest.mark.parametrize(
	"output_type",
	(
		OutputType.ERROR_MESSAGE,
		OutputType.MESSAGE,
		OutputType.WARNING_MESSAGE,
		OutputType.PROGRESS,
		OutputType.DATA,
		OutputType.PROMPT,
	),
)
def test_console_print(capsys: CaptureFixture[str], output_type: OutputType) -> None:
	with patch("sys.stdout.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True):
		for style in None, "red":
			console_print("test", output_type=output_type, style=style)
			captured = capsys.readouterr()
			out = captured.out + captured.err

			if style == "red" or output_type == OutputType.ERROR_MESSAGE:
				assert out == "\x1b[31mtest\x1b[0m\n"
			elif output_type == OutputType.WARNING_MESSAGE:
				assert out == "\x1b[33mtest\x1b[0m\n"
			else:
				assert out == "test\n"


def test_deprecation_warning(capsys: CaptureFixture[str]) -> None:
	with patch("sys.stdout.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True):
		deprecation_warning("This is a deprecation warning")
		captured = capsys.readouterr()
		assert captured.err == "\x1b[33mThis is a deprecation warning\x1b[0m\n"


input_output_testdata = [
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
		"key1;key2;key3\r\nfirst1;first2;1\r\nsecond1;second2;<null>\r\n",
		[{"key1": "first1", "key2": "first2", "key3": True}, {"key1": "second1", "key2": "second2", "key3": None}],
	),
	(
		"csv",
		"key1;key2;key3\r\n1,2,<null>;1,0;{'k1': 'v1', 'k2': 'v2'}\r\n3,4;0;{'k': 'v'}\r\n",
		[
			{"key1": [1, 2, None], "key2": [True, False], "key3": {"k1": "v1", "k2": "v2"}},
			{"key1": [3, 4], "key2": [False], "key3": {"k": "v"}},
		],
	),
	(
		"key-value",
		"key1: 1, 2, \nkey2: true, false\nkey3: {'k1': 'v1', 'k2': 'v2'}\n\nkey1: 3, 4\nkey2: false\nkey3: {'k': 'v'}\n",
		[
			{"key1": [1, 2, None], "key2": [True, False], "key3": {"k1": "v1", "k2": "v2"}},
			{"key1": [3, 4], "key2": [False], "key3": {"k": "v"}},
		],
	),
]
input_testdata = input_output_testdata + [
	(
		"table",
		(
			"╭─────────┬─────────┬────────╮\n"
			"│ key1    │ key2    │ key3   │\n"
			"├─────────┼─────────┼────────┤\n"
			"│ first1  │ ✗ false │ ✓ true │\n"
			"│ second1 │ second2 │        │\n"
			"╰─────────┴─────────┴────────╯\n"
		),
		[{"key1": "first1", "key2": False, "key3": True}, {"key1": "second1", "key2": "second2", "key3": None}],
	)
]


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
def test_output_sort(capsys: CaptureFixture[str], data: Any, expected: Any, sort_by: str) -> None:
	config.set_values({"sort_by": sort_by, "output_format": "json"})
	write_output(data)
	captured = capsys.readouterr()
	assert captured.out.strip() == expected


@pytest.mark.parametrize(
	"data,sort_by,limit,expected",
	[
		(
			[
				{"a": "test_1", "b": "dummy", "c": "string"},
				{"a": "test_2", "b": "aaaa", "c": "boolean"},
				{"a": "test_3", "b": "zzzz", "c": "number"},
			],
			"b",
			2,
			'[{"a":"test_2","b":"aaaa","c":"boolean"},{"a":"test_1","b":"dummy","c":"string"}]',
		),
		(
			[["test_1", "dummy", "string"], ["test_2", "aaaa", "boolean"], ["test_3", "zzzz", "number"]],
			"value1",
			1,
			'[["test_2","aaaa","boolean"]]',
		),
		(
			["test_1", "test_2", "test_3"],
			"value0",
			0,
			"[]",
		),
	],
)
def test_output_limit(capsys: CaptureFixture[str], data: Any, sort_by: str, limit: int, expected: str) -> None:
	config.set_values({"sort_by": sort_by, "limit": limit, "output_format": "json"})
	write_output(data)
	captured = capsys.readouterr()
	assert captured.out.strip() == expected


def test_limit_config_rejects_negative_values() -> None:
	with pytest.raises(ValueError, match="limit must be greater than or equal to 0"):
		config.set_values({"limit": -1})


def test_output_sort_unsupported_data_type() -> None:
	data = {"a": "test_1", "b": "dummy", "c": "string"}
	config.set_values({"sort_by": "b", "output_format": "json"})
	with pytest.raises(RuntimeError):
		write_output(data)


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
	exit_code, stdout, _stderr = run_cli(["--output-format", output_format, "config", "list"])
	print(stdout)
	assert exit_code == 0
	assert any(stdout.startswith(startstring) for startstring in startstrings)
	print("\n\n")
	config.set_values({"output_format": "auto"})  # To not affect following tests


def test_output_config_limit() -> None:
	exit_code, stdout, _stderr = run_cli(["--output-format", "json", "--limit", "2", "config", "list"])
	assert exit_code == 0
	assert len(orjson.loads(stdout)) == 2


@pytest.mark.parametrize(("input_format", "string", "data"), input_output_testdata[:-1])
def test_input(input_format: str, string: str, data: Any) -> None:
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
		old_stdin = sys.stdin
		sys.stdin = inputfile
		result = read_input()
		sys.stdin = old_stdin
		if input_format == "csv":
			for idx, row in enumerate(result):
				for k, v in row.items():
					if v is None:
						continue
					if "," in v:
						# Cannot restore original list from CSV string
						return
					if v == "1":
						row[k] = True
				result[idx] = row
		assert result == data


def test_blocking_input_timeout() -> None:
	class BlockingInput(BytesIO):
		def __init__(self, block_seconds: int) -> None:
			self.block_seconds = block_seconds
			super().__init__()

		def fileno(self) -> int:
			return 0

		def read(self, size: int | None = None) -> bytes:
			time.sleep(self.block_seconds)
			return b""

	with use_logging_config(stderr_level=8):
		for input_file in (None, "-"):
			config.input_file = input_file
			block_seconds = 2
			with TextIOWrapper(BufferedReader(BlockingInput(block_seconds=block_seconds))) as inputfile:
				old_stdin = sys.stdin
				sys.stdin = inputfile
				start = time.time()
				result = read_input()
				wait_time = time.time() - start
				if input_file == "-":
					# If input-file is "-" (stdin set explicitly) the input must block
					assert wait_time >= block_seconds
				else:
					# If input-file is not set, the input should block for 1 second only
					assert wait_time < 0.3
				sys.stdin = old_stdin
				assert result is None


@pytest.mark.parametrize(
	("string", "input_type", "expected_result"), (("teststring", str, "teststring"), ("3.14159", float, 3.14159), ("42", int, 42))
)
def test_prompt(string: str, input_type: type, expected_result: str | float | int) -> None:
	with TextIOWrapper(BufferedReader(BytesIO(string.encode("utf-8")))) as inputfile:
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
				exit_code, _stdout, _stderr = run_cli([f"--output-file={outputfile}", "config", "list"])
				assert exit_code == 0
				assert "log_level" in outputfile.read_text(encoding="utf-8")
			finally:
				outputfile.unlink()

		# --input-file is only used in jsonrpc plugin which requires a server connection


def test_list_attributes() -> None:
	with patch("opsicli.io.write_output") as mock_write_output:
		data = Metadata(
			attributes=[
				Attribute(
					id="id", data_type="str", description="Attribute ID", identifier=True, selected=True, validator=lambda val: str(val)
				),
				Attribute(id="type", data_type="str", description="Data type", selected=False, validator=lambda val: str(val)),
			]
		)
		list_attributes(data)
		mock_write_output.assert_called_once()
		assert mock_write_output.call_args[0][0] == [
			{"id": "id", "type": "str", "description": "Attribute ID", "identifier": True, "selected": True},
			{"id": "type", "type": "str", "description": "Data type", "identifier": False, "selected": False},
		]


def test_write_output_table() -> None:
	metadata = Metadata(
		attributes=[
			Attribute(id="col1", identifier=True, data_type="int"),
			Attribute(id="col2"),
			Attribute(id="col3"),
		]
	)
	col2_data = "a" * 50
	col3_data = "\n".join(5 * ["d" * 50])
	data = [{"col1": row, "col2": col2_data, "col3": col3_data} for row in range(1000)]

	start = time.perf_counter()
	with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
		write_output_table(data, metadata)
		if PLATFORM != "windows":
			lines = mock_stdout.getvalue().split("\n")
			assert len(lines) == 5005
			assert lines[0].startswith("╭")
			assert lines[1].startswith("│")
			assert lines[2].startswith("├")
			assert lines[3].startswith("│")
			assert lines[-2].startswith("╰")
	diff = time.perf_counter() - start
	print(diff / 10)


@pytest.mark.parametrize(
	(
		"config_attributes",
		"metadata_attributes",
		"fallback_attributes",
		"add_identifier",
		"add_attributes",
		"update_selected",
		"expected",
		"expected_config_attributes",
	),
	(
		(
			None,
			[
				Attribute(id="id", identifier=True, selected=True),
				Attribute(id="name", selected=True),
				Attribute(id="description", selected=False),
			],
			None,
			False,
			None,
			False,
			["id", "name"],
			None,
		),
		(
			["all"],
			[
				Attribute(id="id", identifier=True, selected=False),
				Attribute(id="name", selected=False),
				Attribute(id="description", selected=False),
			],
			None,
			False,
			None,
			False,
			["id", "name", "description"],
			["all"],
		),
		(
			["name", "missing"],
			[
				Attribute(id="id", identifier=True, selected=False),
				Attribute(id="name", selected=False),
			],
			None,
			True,
			["extra", "id"],
			False,
			["name", "id"],
			["name", "missing"],
		),
		(
			None,
			[
				Attribute(id="id", identifier=True, selected=False),
				Attribute(id="name", selected=False),
			],
			None,
			False,
			["name", "other"],
			True,
			["name"],
			["name"],
		),
		(
			["custom", "other"],
			[],
			None,
			False,
			["added"],
			True,
			["custom", "other", "added"],
			["custom", "other", "added"],
		),
		(
			None,
			[
				Attribute(id="id", identifier=True, selected=False),
				Attribute(id="name", selected=False),
			],
			["name", "missing"],
			False,
			None,
			False,
			["name"],
			None,
		),
		(
			None,
			[],
			["name", "missing"],
			False,
			None,
			True,
			["name", "missing"],
			["name", "missing"],
		),
	),
)
def test_get_selected_attributes(
	config_attributes: list[str] | None,
	metadata_attributes: list[Attribute],
	fallback_attributes: list[str] | None,
	add_identifier: bool,
	add_attributes: list[str] | None,
	update_selected: bool,
	expected: list[str],
	expected_config_attributes: list[str] | None,
) -> None:
	config.set_values({"attributes": config_attributes})

	result = get_selected_attributes(
		attributes=metadata_attributes,
		fallback_attributes=fallback_attributes,
		add_identifier=add_identifier,
		add_attributes=add_attributes,
		update_selected=update_selected,
	)

	assert result == expected
	assert config.attributes == expected_config_attributes


@pytest.mark.parametrize(
	"configured_timezone, expected_key, expected_offset_seconds, expected_error",
	(
		(None, None, None, None),
		("", None, None, None),
		("UTC", "UTC", 0, None),
		("+00:00", None, 0, None),
		("+01:00", None, 3600, None),
		("-05:30", None, -19800, None),
		("Europe/Berlin", "Europe/Berlin", None, None),
		("Invalid/Timezone", None, None, "Invalid timezone: 'Invalid/Timezone'"),
		("+24:00", None, None, "Invalid timezone: '\\+24:00'"),
	),
)
def test_get_selected_timezone(
	configured_timezone: str | None,
	expected_key: str | None,
	expected_offset_seconds: int | None,
	expected_error: str | None,
) -> None:
	config.set_values({"timezone": configured_timezone})

	if expected_error:
		with pytest.raises(ValueError, match=expected_error):
			get_selected_timezone()
	else:
		result = get_selected_timezone()
		if expected_key is None:
			if configured_timezone in (None, ""):
				assert result is None
			else:
				assert result is not None
		else:
			assert result is not None
			assert getattr(result, "key", None) == expected_key

		if expected_offset_seconds is not None:
			assert result is not None
			assert result.utcoffset(datetime.now()) == timedelta(seconds=expected_offset_seconds)


@pytest.mark.parametrize(
	"value, kwargs, configured_timezone, expected, expected_error",
	(
		(None, {}, None, "", None),
		(None, {"null_format": "<null>"}, None, "<null>", None),
		(True, {}, None, "[bright_green]true[/bright_green]", None),
		(False, {"bool_format": "true_false_symbols"}, None, "[bright_black]✗ false[/bright_black]", None),
		(True, {"bool_format": "1_0"}, None, "1", None),
		([1, None, "abc"], {}, None, "1, , abc", None),
		([1, 2, 3], {"list_format": "comma_separated"}, None, "1,2,3", None),
		([1, 2], {"list_format": "square_brackets"}, None, "[1, 2]", None),
		(str, {}, None, "str", None),
		("custom", {"value_styles": {"custom": "blue"}}, None, "[blue]custom[/blue]", None),
		(
			datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc),
			{},
			"Europe/Berlin",
			"2025-01-15T13:30:00+01:00",
			None,
		),
		(
			datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc),
			{},
			"+01:00",
			"2025-01-15T13:30:00+01:00",
			None,
		),
		(
			datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc),
			{},
			"Invalid/Timezone",
			None,
			"Invalid timezone: 'Invalid/Timezone'",
		),
	),
)
def test_to_string(
	value: Any,
	kwargs: dict[str, Any],
	configured_timezone: str | None,
	expected: str | None,
	expected_error: str | None,
) -> None:
	config.set_values({"timezone": configured_timezone})
	if expected_error:
		with pytest.raises(ValueError, match=expected_error):
			to_string(value, **kwargs)
	else:
		assert to_string(value, **kwargs) == expected


def test_get_separated_entries() -> None:
	assert get_separated_entries("1, 2, 3") == ["1", "2", "3"]
	assert get_separated_entries("    1,2   ,     3    ") == ["1", "2", "3"]
	old_separator = config.get_values().get("input_separator")
	try:
		config.set_values({"input_separator": ";"})
		assert get_separated_entries("1; 2; 3") == ["1", "2", "3"]
	finally:
		config.set_values({"input_separator": old_separator})


@pytest.mark.opsi_service
@pytest.mark.parametrize("input_separator", (None, " ", ",", ";", "|", ":", "#", "/"))
def test_input_separator(input_separator: str) -> None:
	effective_input_separator = input_separator if input_separator is not None else config.get_values().get("input_separator")
	client_list = f"client1.test.local{effective_input_separator}client2.test.local{effective_input_separator}client3.test.local"
	args = ["--dry-run", "client-action", "--clients", client_list, "set-action-request"]
	if input_separator is not None:
		args = ["--input-separator", input_separator] + args
	_, stdout, stderr = run_cli(args)
	for client in ("client1.test.local", "client2.test.local", "client3.test.local"):
		assert f"'{client}'" in stderr
