# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

input output
"""

import csv
import inspect
import sys
from contextlib import contextmanager
from io import BytesIO, StringIO
from typing import IO, Any, Iterator, Type

import msgpack  # type: ignore[import]
import orjson
from opsicommon.logging import get_logger
from rich import print_json  # type: ignore[import]
from rich.console import Console  # type: ignore[import]
from rich.prompt import FloatPrompt, IntPrompt, Prompt  # type: ignore[import]
from rich.table import Table, box  # type: ignore[import]

from opsicli.config import config

logger = get_logger("opsicli")


def get_attributes(data: list[dict[str, Any]], all_elements: bool = True) -> list[str]:
	attributes_set = set()
	for element in data:
		attributes_set |= set(element)
		if not all_elements:
			break
	attributes = sorted(list(attributes_set))
	if len(attributes) > 1:
		try:
			# Move attribute id to first position
			attributes.insert(0, attributes.pop(attributes.index("id")))
		except ValueError:
			pass
	return attributes


def get_structure_type(data: list | dict) -> type[list] | type[dict] | None:
	if isinstance(data, list):
		if data and isinstance(data[0], list):
			return list[list]
		if data and isinstance(data[0], dict):
			return list[dict]
		return list
	if isinstance(data, dict):
		return dict
	return None


def output_file_is_stdout() -> bool:
	return str(config.output_file) in ("-", "")


def output_file_is_a_tty() -> bool:
	if output_file_is_stdout():
		if sys.stdout.isatty():
			logger.debug("output_file stdout is a tty")
			return True
		logger.debug("output_file stdout is not a tty")
		return False
	logger.debug("output_file is not a tty")
	return False


@contextmanager
def output_file_bin() -> Iterator[IO[bytes]]:
	if str(config.output_file) in ("-", ""):
		yield sys.stdout.buffer
		sys.stdout.flush()
	else:
		with open(config.output_file, mode="wb") as file:
			yield file
			file.flush()


@contextmanager
def output_file_str(encoding: str | None = "utf-8") -> Iterator[IO[str]]:
	encoding = encoding or "utf-8"
	if str(config.output_file) in ("-", ""):
		yield sys.stdout
		sys.stdout.flush()
	else:
		with open(config.output_file, mode="w", encoding=encoding) as file:
			yield file
			file.flush()


def get_console(file: IO[str] | None = None) -> Console:
	return Console(file=file, color_system="auto" if config.color else None)


def prompt(  # pylint: disable=too-many-arguments
	text: str,
	return_type: type = str,
	password: bool = False,
	default: Any = ...,
	choices: list[str] | None = None,
	show_default: bool = True,
	show_choices: bool = True,
) -> str | int | float:
	cls: Type[Prompt] | Type[IntPrompt] | Type[FloatPrompt] = Prompt
	if return_type == int:
		cls = IntPrompt
	elif return_type == float:
		cls = FloatPrompt
	return cls.ask(
		prompt=text,
		console=get_console(),
		default=default,
		password=password,
		choices=choices,
		show_default=show_default,
		show_choices=show_choices,
	)


def write_output_table(data: Any, metadata: dict) -> None:
	def to_string(value: Any) -> str:
		if value is None:
			return ""
		if isinstance(value, bool):
			return "true" if value else "false"
		if isinstance(value, (list, tuple)):
			return ", ".join([to_string(v) for v in value])
			# return str([to_string(v) for v in value])
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	attributes = config.attributes or []
	table = Table(box=box.ROUNDED, show_header=config.header, show_lines=False)
	row_ids = []
	for column in metadata["attributes"]:
		if attributes == ["all"] or column["id"] in attributes or (not attributes and column.get("selected", True)):
			style = "cyan" if column.get("identifier") else None
			no_wrap = bool(column.get("identifier"))
			table.add_column(header=column["id"], style=style, no_wrap=no_wrap)
			row_ids.append(column["id"])

	for row in data:
		if isinstance(row, dict):
			table.add_row(*[to_string(row.get(rid)) for rid in row_ids])
		elif isinstance(row, list):
			table.add_row(*[to_string(el) for el in row])
		else:
			table.add_row(*[to_string(row)])

	with output_file_str() as file:
		console = get_console(file)
		console.print(table)


def write_output_csv(data: Any, metadata: dict) -> None:
	def to_string(value: Any) -> str:
		if value is None:
			return "<null>"
		if isinstance(value, bool):
			return "1" if value else "0"
		if isinstance(value, (list, tuple)):
			return ",".join([to_string(v) for v in value])
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file_str() as file:
		writer = csv.writer(file, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
		row_ids = []
		header = []
		attributes = config.attributes or []
		for column in metadata["attributes"]:
			if attributes == ["all"] or column["id"] in attributes or (not attributes and column.get("selected", True)):
				row_ids.append(column["id"])
				header.append(column["id"])
		if config.header:
			writer.writerow(header)
		for row in data:
			if isinstance(row, dict):
				writer.writerow([to_string(row.get(rid)) for rid in row_ids])
			elif isinstance(row, list):
				writer.writerow([to_string(el) for el in row])
			else:
				writer.writerow([to_string(row)])


def write_output_json(data: Any, metadata: dict | None = None, pretty: bool = False) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	option = 0
	if pretty and not output_file_is_a_tty():
		option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2  # pylint: disable=no-member

	json = orjson.dumps(  # pylint: disable=no-member
		{"metadata": metadata, "data": data} if config.metadata and metadata else data, default=to_string, option=option
	)

	if pretty and output_file_is_a_tty():
		print_json(json.decode("utf-8"))
	else:
		with output_file_bin() as file:
			file.write(json)


def write_output_msgpack(data: Any, metadata: dict | None = None) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file_bin() as file:
		file.write(msgpack.dumps({"metadata": metadata, "data": data} if config.metadata and metadata else data, default=to_string))


def write_output(data: Any, metadata: dict | None = None, default_output_format: str | None = None) -> None:
	output_format = config.output_format
	if output_format == "auto":
		output_format = default_output_format if default_output_format else "table"

	if output_format in ("table", "csv") and not metadata:
		stt = get_structure_type(data)
		if stt == list:
			metadata = {"attributes": [{"id": "value0"}]}
		elif stt == list[list]:
			metadata = {"attributes": [{"id": f"value{idx}"} for idx in range(len(data[0]))]}
		elif stt == list[dict]:
			metadata = {"attributes": [{"id": key} for key in get_attributes(data)]}
		else:
			raise RuntimeError(f"Output-format {config.output_format!r} does not support stucture {stt!r}")

	if output_format in ("table"):
		assert metadata
		write_output_table(data, metadata)
	elif output_format == "csv":
		assert metadata
		write_output_csv(data, metadata)
	elif output_format in ("json", "pretty-json"):
		write_output_json(data, metadata, output_format == "pretty-json")
	elif output_format == "msgpack":
		write_output_msgpack(data, metadata)
	else:
		raise ValueError(f"Invalid output-format: {output_format}")


def write_output_raw(data: bytes | str) -> None:
	if isinstance(data, bytes):
		with output_file_bin() as file:
			file.write(data)
	else:
		with output_file_str() as file:
			file.write(data)


def input_file_is_stdin() -> bool:
	return str(config.input_file) in ("-", "")


def input_file_is_a_tty() -> bool:
	if input_file_is_stdin():
		if sys.stdin.isatty():
			logger.debug("input_file stdin is a tty")
			return True
		logger.debug("input_file stdin is not a tty")
		return False
	logger.debug("input_file is not a tty")
	return False


@contextmanager
def input_file_bin() -> Iterator[IO[bytes]]:
	if str(config.input_file) in ("-", ""):
		if input_file_is_a_tty():
			yield BytesIO()
		else:
			yield sys.stdin.buffer
	else:
		with open(config.input_file, mode="rb") as file:
			yield file


@contextmanager
def input_file_str(encoding: str | None = "utf-8") -> Iterator[IO[str]]:
	encoding = encoding or "utf-8"
	if str(config.input_file) in ("-", ""):
		if input_file_is_a_tty():
			yield StringIO()
		else:
			yield sys.stdin
	else:
		with open(config.input_file, mode="r", encoding=encoding) as file:
			yield file


def read_input_raw_bin() -> bytes:
	with input_file_bin() as file:
		return file.read()


def read_input_raw_str(encoding: str | None = "utf-8") -> str:
	with input_file_str(encoding) as file:
		return file.read()


def read_input_msgpack(data: bytes) -> Any:
	data = msgpack.loads(data)
	if isinstance(data, dict) and "metadata" in data and "data" in data and not config.metadata:
		return data["data"]
	return data


def read_input_json(data: bytes) -> Any:
	data = orjson.loads(data)  # pylint: disable=no-member
	if isinstance(data, dict) and "metadata" in data and "data" in data and not config.metadata:
		return data["data"]
	return data


def read_input_csv(data: bytes) -> list[dict | list[str]]:
	rows: list[dict | list[str]] = []
	header = []
	reader = csv.reader(data.decode("utf-8").split("\n"), delimiter=";", quotechar='"')
	for idx, row in enumerate(reader):
		if config.header and idx == 0:
			header = row
			continue
		for cidx, val in enumerate(row):
			if val == "<null>":
				row[cidx] = None  # type: ignore[call-overload]
		if row:
			if header:
				rows.append({header[i]: row[i] for i in range(len(header))})
			else:
				rows.append(row)
	return rows


def read_input() -> Any:
	with input_file_bin() as file:
		data = file.read()
	if not data:
		return None

	try:
		logger.debug("Trying msgpack")
		return read_input_msgpack(data)
	except (ValueError, msgpack.exceptions.UnpackException):
		try:
			logger.debug("Trying json")
			return read_input_json(data)
		except orjson.JSONDecodeError:  # pylint: disable=no-member
			logger.debug("Trying csv")
			return read_input_csv(data)
