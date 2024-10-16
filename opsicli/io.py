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
from dataclasses import asdict, dataclass, field
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


@dataclass
class Attribute:
	id: str
	description: str | None = None
	identifier: bool = False
	selected: bool = True
	data_type: str | None = None

	def as_dict(self) -> dict[str, str | bool]:
		return asdict(self)


@dataclass
class Metadata:
	attributes: list[Attribute] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		return asdict(self)


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


def sort_data(data: Any) -> Any:
	data_type = get_structure_type(data)
	if data_type == list[dict]:
		return sorted(data, key=lambda x: str(x.get(config.sort_by)))
	elif data_type in (list[list], list):
		# Extract index from sort_by value in "valueX" format
		index = int(config.sort_by.replace("value", "")) if config.sort_by.startswith("value") else 0
		return sorted(data, key=lambda x: str(x[index]) if data_type == list[list] else x)
	else:
		raise RuntimeError(f"Sort-By {config.sort_by!r} does not support structure {data_type!r}")


def output_file_is_stdout() -> bool:
	return not config.output_file or str(config.output_file) == "-"


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
	if not config.output_file or str(config.output_file) == "-":
		yield sys.stdout.buffer
		sys.stdout.flush()
	else:
		with open(config.output_file, mode="wb") as file:
			yield file
			file.flush()


@contextmanager
def output_file_str(encoding: str | None = "utf-8") -> Iterator[IO[str]]:
	encoding = encoding or "utf-8"
	if not config.output_file or str(config.output_file) == "-":
		yield sys.stdout
		sys.stdout.flush()
	else:
		with open(config.output_file, mode="w", encoding=encoding) as file:
			yield file
			file.flush()


class QuietConsole(Console):
	def print(self, *args: Any, **kwargs: Any) -> None:
		"""
		Override get_console.print() method to not print anything
		"""
		pass


def get_console(file: IO[str] | None = None, ignore_quiet: bool = False) -> Console:
	if (file is not sys.stderr or config.hide_errors) and config.quiet and not ignore_quiet:
		return QuietConsole(file=file, color_system="auto" if config.color else None)
	return Console(file=file, color_system="auto" if config.color else None)


def console_print(*args: Any, **kwargs: Any) -> None:
	"""
	Print to console
	"""
	get_console().print(*args, **kwargs)


def prompt(
	text: str,
	return_type: type = str,
	password: bool = False,
	default: Any = ...,
	choices: list[str] | None = None,
	show_default: bool = True,
	show_choices: bool = True,
) -> str | int | float:
	cls: Type[Prompt] | Type[IntPrompt] | Type[FloatPrompt] = Prompt
	if return_type == int:  # noqa: E721
		cls = IntPrompt
	elif return_type == float:  # noqa: E721
		cls = FloatPrompt
	return cls.ask(
		prompt=text,
		console=get_console(ignore_quiet=True),
		default=default,
		password=password,
		choices=choices,
		show_default=show_default,
		show_choices=show_choices,
	)


def write_output_table(data: Any, metadata: Metadata) -> None:
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
	for attribute in metadata.attributes:
		if attributes == ["all"] or attribute.id in attributes or (not attributes and attribute.selected):
			style = "cyan" if attribute.identifier else None
			no_wrap = bool(attribute.identifier)
			table.add_column(header=attribute.id, style=style, no_wrap=no_wrap)
			row_ids.append(attribute.id)

	for row in data:
		if isinstance(row, dict):
			table.add_row(*[to_string(row.get(rid)) for rid in row_ids])
		elif isinstance(row, list):
			table.add_row(*[to_string(el) for el in row])
		else:
			table.add_row(*[to_string(row)])

	with output_file_str() as file:
		console = get_console(file, ignore_quiet=True)
		console.print(table)


def write_output_csv(data: Any, metadata: Metadata) -> None:
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
		for attribute in metadata.attributes:
			if attributes == ["all"] or attribute.id in attributes or (not attributes and attribute.selected):
				row_ids.append(attribute.id)
				header.append(attribute.id)
		if config.header:
			writer.writerow(header)
		for row in data:
			if isinstance(row, dict):
				writer.writerow([to_string(row.get(rid)) for rid in row_ids])
			elif isinstance(row, list):
				writer.writerow([to_string(el) for el in row])
			else:
				writer.writerow([to_string(row)])


def write_output_json(data: Any, metadata: Metadata | None = None, pretty: bool = False) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	option = 0
	if pretty and not output_file_is_a_tty():
		option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2

	json = orjson.dumps(
		{"metadata": metadata.as_dict(), "data": data} if config.metadata and metadata else data, default=to_string, option=option
	)

	if pretty and output_file_is_a_tty():
		print_json(json.decode("utf-8"), highlight=config.color)
	else:
		with output_file_bin() as file:
			file.write(json)


def write_output_msgpack(data: Any, metadata: Metadata | None = None) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file_bin() as file:
		file.write(
			msgpack.dumps({"metadata": metadata.as_dict(), "data": data} if config.metadata and metadata else data, default=to_string)
		)


def write_output(data: Any, metadata: Metadata | None = None, default_output_format: str | None = None) -> None:
	output_format = config.output_format
	if output_format == "auto":
		output_format = default_output_format if default_output_format else "table"

	if output_format in ("table", "csv") and not metadata:
		stt = get_structure_type(data)
		if stt == list:  # noqa: E721
			metadata = Metadata(attributes=[Attribute(id="value0")])
		elif stt == list[list]:
			metadata = Metadata(attributes=[Attribute(id=f"value{idx}") for idx in range(len(data[0]))])
		elif stt == list[dict]:
			metadata = Metadata(attributes=[Attribute(id=key) for key in get_attributes(data)])
		else:
			raise RuntimeError(f"Output-format {output_format!r} does not support stucture {stt!r}")

	if metadata is not None and config.attributes and config.attributes != ["all"]:
		ordered_list = [attr for config_attribute in config.attributes for attr in metadata.attributes if attr.id == config_attribute]
		remaining_list = [attr for attr in metadata.attributes if attr.id not in config.attributes]
		metadata.attributes = ordered_list + remaining_list

	if config.sort_by:
		data = sort_data(data)

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
	return not config.input_file or str(config.input_file) == "-"


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
	if not config.input_file or str(config.input_file) == "-":
		if input_file_is_a_tty():
			logger.debug("Binary input from tty")
			yield BytesIO()
		else:
			logger.debug("Binary input from stdin")
			yield sys.stdin.buffer
	else:
		logger.debug("Binary input from file '%s'", config.input_file)
		with open(config.input_file, mode="rb") as file:
			yield file


@contextmanager
def input_file_str(encoding: str | None = "utf-8") -> Iterator[IO[str]]:
	encoding = encoding or "utf-8"
	if not config.input_file or str(config.input_file) == "-":
		if input_file_is_a_tty():
			logger.debug("String input from tty")
			yield StringIO()
		else:
			logger.debug("String input from stdin")
			yield sys.stdin
	else:
		logger.debug("String input from file '%s'", config.input_file)
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
	data = orjson.loads(data)
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


def stdin_readable(timeout: float) -> bool:
	if sys.platform == "win32":
		import pywintypes
		import win32api
		import win32event
		import win32file

		try:
			win32file.FlushFileBuffers(win32api.STD_INPUT_HANDLE)
		except pywintypes.error:
			pass
		return win32event.WaitForSingleObject(win32api.STD_INPUT_HANDLE, int(timeout * 1000)) == win32event.WAIT_OBJECT_0
	else:
		import select

		rlist, _, _ = select.select([sys.stdin], [], [], timeout)
		return bool(rlist)


def read_input() -> Any:
	logger.debug("Reading input")
	with input_file_bin() as file:
		data = b""
		if not config.input_file and not input_file_is_a_tty():
			logger.debug("No input file explicitly set, checking if stdin is readable")
			try:
				is_readable = stdin_readable(0.1)
				if is_readable:
					logger.debug("Stdin is readable, reading input from stdin")
					data += file.read(1)
					if not data:
						logger.debug("No data read from stdin, returning None")
						return None
				else:
					logger.debug("Stdin is not readable, returning None")
					return None
			except io.UnsupportedOperation as err:
				logger.debug("Failed to check stdin readability: %s", err)

		logger.debug("Reading input from %s", file)
		data += file.read()
	if not data:
		return None

	try:
		logger.debug("Trying msgpack")
		return read_input_msgpack(data)
	except (ValueError, msgpack.exceptions.UnpackException):
		try:
			logger.debug("Trying json")
			return read_input_json(data)
		except orjson.JSONDecodeError:
			logger.debug("Trying csv")
			return read_input_csv(data)


def list_attributes(data: Metadata) -> None:
	attributes_list = [
		{"id": attribute.id, "type": attribute.data_type} for attribute in data.attributes if attribute.selected is not False
	]
	write_output(attributes_list, None, "table")
