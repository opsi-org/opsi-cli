# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import sys
import csv
import orjson
import msgpack
import inspect
from typing import IO, Any, Optional

from rich.console import Console
from rich.table import Table
from opsicli.config import config

__version__ = "0.1.0"


def get_console(file: Optional[IO[str]] = None):
	return Console(file=file or sys.stdout, color_system="auto" if config.color else None)


def write_output_table(file: IO[str], meta_data, data) -> None:
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

	table = Table()
	row_ids = []
	for column in meta_data["columns"]:
		style = "cyan" if column.get("identifier") else None
		no_wrap = bool(column.get("identifier"))
		table.add_column(header=column.get("title", column.get("id")), style=style, no_wrap=no_wrap)
		row_ids.append(column.get("id"))

	for row in data:
		table.add_row(*[to_string(row[rid]) for rid in row_ids])

	get_console(file).print(table)


def write_output_csv(file: IO[str], meta_data, data) -> None:
	def to_string(value):
		if value is None:
			return ""
		if isinstance(value, bool):
			return 1 if value else 0
		if isinstance(value, (list, tuple)):
			return ",".join([to_string(v) for v in value])
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	writer = csv.writer(file, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
	row_ids = []
	header = []
	for column in meta_data["columns"]:
		row_ids.append(column.get("id"))
		header.append(column.get("title", column.get("id")))
	writer.writerow(header)
	for row in data:
		writer.writerow([to_string(row[rid]) for rid in row_ids])


def write_output_json(file: IO[str], meta_data, data, pretty=False) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	option = 0
	if pretty:
		option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2  # pylint: disable=no-member
	file.buffer.write(  # type: ignore[attr-defined]
		orjson.dumps({"meta_data": meta_data, "data": data}, default=to_string, option=option)  # pylint: disable=no-member
	)


def write_output_msgpack(file: IO[str], meta_data, data) -> None:
	def to_string(value):
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	file.buffer.write(msgpack.dumps({"meta_data": meta_data, "data": data}, default=to_string))  # type: ignore[attr-defined]  # pylint: disable=no-member


def write_output(meta_data, data) -> None:
	file = sys.stdout
	if config.output_format in ("auto", "table"):
		write_output_table(file, meta_data, data)
	elif config.output_format in ("json", "pretty-json"):
		write_output_json(file, meta_data, data, config.output_format == "pretty-json")
	elif config.output_format == "msgpack":
		write_output_msgpack(file, meta_data, data)
	elif config.output_format == "csv":
		write_output_csv(file, meta_data, data)


def prepare_cli_paths() -> None:
	for plugin_dir in config.plugin_dirs:
		if not plugin_dir.exists():
			plugin_dir.mkdir(parents=True)
			# print("making", plugin_dir)
	if not config.lib_dir.exists():
		config.lib_dir.mkdir(parents=True)
		# print("making", lib_dir)
	if str(config.lib_dir) not in sys.path:
		sys.path.append(str(config.lib_dir))
	# print("path:", sys.path)
