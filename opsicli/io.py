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
		idx = attributes.index("id")
		if idx > 0:
			attributes.insert(0, attributes.pop(idx))
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

	table = Table(box=box.ROUNDED, show_header=config.header)
	row_ids = []
	for column in metadata["columns"]:
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
		for column in metadata["columns"]:
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


def write_output_json(data: Any, metadata: Dict, pretty: bool = False) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	option = 0
	if pretty:
		option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2  # pylint: disable=no-member

	with output_file(encoding="binary") as file:
		file.write(  # type: ignore[attr-defined]
			orjson.dumps(  # pylint: disable=no-member
				{"metadata": metadata, "data": data} if config.metadata else data, default=to_string, option=option
			)
		)


def write_output_msgpack(data: Any, metadata: Dict) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file(encoding="binary") as file:
		file.write(  # type: ignore[attr-defined]  # pylint: disable=no-member
			msgpack.dumps({"metadata": metadata, "data": data} if config.metadata else data, default=to_string)
		)


def write_output(data: Any, metadata: Optional[Dict] = None) -> None:
	if not data:
		return
	if not metadata:
		stt = get_structure_type(data)
		if stt == List:
			metadata = {"columns": [{"id": "value0"}]}
		elif stt == List[List]:
			metadata = {"columns": [{"id": f"value{idx}"} for idx in range(len(data[0]))]}
		elif stt == List[Dict]:
			metadata = {"columns": [{"id": key} for key in get_attributes(data)]}
		else:
			raise RuntimeError(f"Output-format {config.output_format!r} does not support stucture {stt!r}")

	if config.output_format in ("auto", "table"):
		write_output_table(data, metadata)
	elif config.output_format in ("json", "pretty-json"):
		write_output_json(data, metadata, config.output_format == "pretty-json")
	elif config.output_format == "msgpack":
		write_output_msgpack(data, metadata)
	elif config.output_format == "csv":
		write_output_csv(data, metadata)
	else:
		raise ValueError(f"Invalid output-format: {config.output_format}")


def write_output_raw(data: Union[bytes, str]) -> None:
	encoding = "binary" if isinstance(data, bytes) else "utf-8"
	with output_file(encoding=encoding) as file:
		file.write(data)


@contextmanager
def input_file(encoding: Optional[str] = None):
	if str(config.input_file) in ("-", ""):
		if sys.stdin.isatty():
			logger.debug("stdin is a tty")
			if encoding == "binary":
				yield io.BytesIO()
			else:
				yield io.StringIO()
		else:
			logger.debug("stdin is not a tty")
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


def read_input_msgpack(data: bytes) -> None:
	data = msgpack.loads(data)
	if isinstance(data, dict) and "metadata" in data and "data" in data and not config.metadata:
		return data["data"]
	return data


def read_input_json(data: bytes) -> None:
	data = orjson.loads(data)  # pylint: disable=no-member
	if isinstance(data, dict) and "metadata" in data and "data" in data and not config.metadata:
		return data["data"]
	return data


def read_input_csv(data: bytes) -> None:
	rows = []
	header = []
	reader = csv.reader(data.decode("utf-8").split("\n"), delimiter=";", quotechar='"')
	for idx, row in enumerate(reader):
		if config.header and idx == 0:
			header = row
			continue
		for cidx, val in enumerate(row):
			if val == "<null>":
				row[cidx] = None
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
