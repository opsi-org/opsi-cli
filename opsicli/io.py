# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

input output
"""

import csv
import inspect
import io
import sys
from contextlib import contextmanager
from typing import IO, Any, Dict, List, Optional, Union

import msgpack  # type: ignore[import]
import orjson
from opsicommon.logging import logger  # type: ignore[import]
from rich import print_json
from rich.console import Console
from rich.table import Table, box

from opsicli.config import config


def get_attributes(data, all_elements=True) -> List[str]:
	attributes_set = set()
	for element in data:
		attributes_set |= set(element.keys())
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


def get_structure_type(data):
	if isinstance(data, list):
		if data and isinstance(data[0], list):
			return List[List]
		if data and isinstance(data[0], dict):
			return List[Dict]
		return List
	if isinstance(data, dict):
		return Dict
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
def output_file(encoding: Optional[str] = "utf-8"):
	if str(config.output_file) in ("-", ""):
		if encoding == "binary":
			yield sys.stdout.buffer
		else:
			yield sys.stdout
		sys.stdout.flush()
	else:
		mode = "w"
		if encoding == "binary":
			mode = "wb"
		with open(config.output_file, mode=mode, encoding=None if encoding == "binary" else encoding) as file:
			yield file
			file.flush()


def get_console(file: IO[str] = None):
	return Console(file=file, color_system="auto" if config.color else None)


def write_output_table(data: Any, metadata: Dict) -> None:
	def to_string(value):
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
	table = Table(box=box.ROUNDED, show_header=config.header)
	row_ids = []
	for column in metadata["attributes"]:
		if attributes == ["all"] or column["id"] in attributes or (not attributes and column.get("selected", True)):
			style = "cyan" if column.get("identifier") else None
			no_wrap = bool(column.get("identifier"))
			table.add_column(header=column.get("title", column["id"]), style=style, no_wrap=no_wrap)
			row_ids.append(column["id"])

	for row in data:
		if isinstance(row, dict):
			table.add_row(*[to_string(row.get(rid)) for rid in row_ids])
		elif isinstance(row, list):
			table.add_row(*[to_string(el) for el in row])
		else:
			table.add_row(*[to_string(row)])

	with output_file() as file:
		get_console(file).print(table)


def write_output_csv(data: Any, metadata: Dict) -> None:
	def to_string(value):
		if value is None:
			return "<null>"
		if isinstance(value, bool):
			return "1" if value else "0"
		if isinstance(value, (list, tuple)):
			return ",".join([to_string(v) for v in value])
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file() as file:
		writer = csv.writer(file, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
		row_ids = []
		header = []
		attributes = config.attributes or []
		for column in metadata["attributes"]:
			if attributes == ["all"] or column["id"] in attributes or (not attributes and column.get("selected", True)):
				row_ids.append(column["id"])
				# header.append(column.get("title", column["id"])
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


def write_output_json(data: Any, metadata: Optional[Dict] = None, pretty: bool = False) -> None:
	def to_string(value):
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
		with output_file(encoding="binary") as file:
			file.write(json)  # type: ignore[attr-defined]


def write_output_msgpack(data: Any, metadata: Optional[Dict] = None) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file(encoding="binary") as file:
		file.write(  # type: ignore[attr-defined]  # pylint: disable=no-member
			msgpack.dumps({"metadata": metadata, "data": data} if config.metadata and metadata else data, default=to_string)
		)


def write_output(data: Any, metadata: Optional[Dict] = None, default_output_format: Optional[str] = None) -> None:
	output_format = config.output_format
	if output_format == "auto":
		output_format = default_output_format if default_output_format else "table"

	if output_format in ("table", "csv") and not metadata:
		stt = get_structure_type(data)
		if stt == List:
			metadata = {"attributes": [{"id": "value0"}]}
		elif stt == List[List]:
			metadata = {"attributes": [{"id": f"value{idx}"} for idx in range(len(data[0]))]}
		elif stt == List[Dict]:
			metadata = {"attributes": [{"id": key} for key in get_attributes(data)]}
		else:
			raise RuntimeError(f"Output-format {config.output_format!r} does not support stucture {stt!r}")

	if output_format in ("table"):
		write_output_table(data, metadata)  # type: ignore[arg-type]
	elif output_format == "csv":
		write_output_csv(data, metadata)  # type: ignore[arg-type]
	elif output_format in ("json", "pretty-json"):
		write_output_json(data, metadata, output_format == "pretty-json")
	elif output_format == "msgpack":
		write_output_msgpack(data, metadata)
	else:
		raise ValueError(f"Invalid output-format: {output_format}")


def write_output_raw(data: Union[bytes, str]) -> None:
	encoding = "binary" if isinstance(data, bytes) else "utf-8"
	with output_file(encoding=encoding) as file:
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
def input_file(encoding: Optional[str] = None):
	if str(config.input_file) in ("-", ""):
		if input_file_is_a_tty():
			if encoding == "binary":
				yield io.BytesIO()
			else:
				yield io.StringIO()
		else:
			if encoding == "binary":
				yield sys.stdin.buffer
			else:
				yield sys.stdin
	else:
		mode = "r"
		if encoding == "binary":
			mode = "rb"
		with open(config.input_file, mode=mode, encoding=None if encoding == "binary" else encoding) as file:
			yield file


def read_input_raw(encoding: Optional[str] = None) -> str:
	with input_file(encoding) as file:
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


def read_input_csv(data: bytes) -> List[Union[Dict, List[str]]]:
	rows: List[Union[Dict, List[str]]] = []
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
	with input_file(encoding="binary") as file:
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
