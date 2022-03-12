# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import csv
import inspect
import sys
from typing import IO, Any, Optional, Union

import msgpack  # type: ignore[import]
import orjson
from rich.console import Console
from rich.table import Table, box

from opsicli.config import config

__version__ = "0.1.0"


def get_console(file: Optional[IO[str]] = None):
	return Console(file=file or sys.stdout, color_system="auto" if config.color else None)


def write_output_table(file: IO[str], metadata, data) -> None:
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

	get_console(file).print(table)


def write_output_csv(file: IO[str], metadata, data) -> None:
	def to_string(value):
		if value is None:
			return ""
		if isinstance(value, bool):
			return "1" if value else "0"
		if isinstance(value, (list, tuple)):
			return ",".join([to_string(v) for v in value])
		if inspect.isclass(value):
			return value.__name__
		return str(value)

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


def write_output_json(file: IO[str], metadata, data, pretty=False) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	option = 0
	if pretty:
		option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2  # pylint: disable=no-member
	file.buffer.write(  # type: ignore[attr-defined]
		orjson.dumps(  # pylint: disable=no-member
			{"metadata": metadata, "data": data} if config.metadata else data, default=to_string, option=option
		)
	)


def write_output_msgpack(file: IO[str], metadata, data) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	file.buffer.write(  # type: ignore[attr-defined]  # pylint: disable=no-member
		msgpack.dumps({"metadata": metadata, "data": data} if config.metadata else data, default=to_string)
	)


def write_output(metadata, data) -> None:
	file = sys.stdout
	if str(config.output_file) not in ("-", ""):
		file = open(config.output_file, "w", encoding="utf-8")  # pylint: disable=consider-using-with
	try:
		if config.output_format in ("auto", "table"):
			write_output_table(file, metadata, data)
		elif config.output_format in ("json", "pretty-json"):
			write_output_json(file, metadata, data, config.output_format == "pretty-json")
		elif config.output_format == "msgpack":
			write_output_msgpack(file, metadata, data)
		elif config.output_format == "csv":
			write_output_csv(file, metadata, data)
	finally:
		if file != sys.stdout:
			file.close()


def write_output_raw(data: Union[bytes, str]) -> None:
	if str(config.output_file) in ("-", ""):
		if isinstance(data, bytes):
			sys.stdout.buffer.write(data)
		else:
			sys.stdout.write(data)
	else:
		if isinstance(data, bytes):
			with open(config.output_file, "wb") as file:
				file.write(data)
		else:
			with open(config.output_file, "w", encoding="utf-8") as file:
				file.write(data)


def prepare_cli_paths() -> None:
	for plugin_dir in config.plugin_dirs:
		if not plugin_dir.exists():
			plugin_dir.mkdir(parents=True)
			# print("making", plugin_dir)
	if not config.python_lib_dir.exists():
		config.python_lib_dir.mkdir(parents=True)
		# print("making", python_lib_dir)
	if str(config.python_lib_dir) not in sys.path:
		sys.path.append(str(config.python_lib_dir))
	# print("path:", sys.path)
