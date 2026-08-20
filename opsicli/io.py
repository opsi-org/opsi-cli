# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

input output
"""

import csv
import inspect
import io
import os
import re
import shlex
import shutil
import sys
import zoneinfo
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from io import BytesIO, StringIO
from typing import IO, Any, Literal

import msgpack
import orjson
from opsi.logging import get_logger
from opsi.system.info import is_windows
from rich import print_json
from rich.color import ANSI_COLOR_NAMES
from rich.console import Console
from rich.progress import Progress
from rich.prompt import FloatPrompt, IntPrompt, Prompt
from rich.table import Table, box
from rich.text import Text

from opsicli.config import config
from opsicli.types import OutputFormat

logger = get_logger("opsicli")

LOG_COLORS = {
	"9": "#D500F9",  # SECRET
	"8": "#8B8B8B",  # TRACE
	"7": "#C0C0C0",  # DEBUG
	"6": "#F5F5F5",  # INFO
	"5": "#009605",  # NOTICE
	"4": "#FF9100",  # WARNING
	"3": "#E51D3B",  # ERROR
	"2": "#E20066",  # CRITICAL
	"1": "#2979FF",  # ESSENTIAL
}

COLORS = [
	c
	for c in ANSI_COLOR_NAMES
	if "white" not in c and "black" not in c and "red" not in c and "grey" not in c and "gray" not in c and "bright" not in c
]

DEFAULT_VALUE_STYLES = {
	"true": "bright_green",
	"✓ true": "bright_green",
	"false": "bright_black",
	"✗ false": "bright_black",
}


class OutputType(StrEnum):
	MESSAGE = "message"
	WARNING_MESSAGE = "warning_message"
	ERROR_MESSAGE = "error_message"
	PROGRESS = "progress"
	PROMPT = "prompt"
	DATA = "data"


@dataclass
class Attribute:
	id: str
	description: str | None = None
	identifier: bool = False
	selected: bool = True
	data_type: str | None = None
	column_style: str | None = None
	value_style: dict[str, str] | None = None
	validator: Callable[[Any], Any] | None = None

	def as_dict(self, *, exclude_fields: Iterable[str] | None = None) -> dict[str, str | bool]:
		_dict = asdict(self)
		for attr in exclude_fields or []:
			if attr in _dict:
				del _dict[attr]
		return _dict


@dataclass
class Metadata:
	attributes: list[Attribute] = field(default_factory=list)

	def as_dict(self, *, exclude_attribute_fields: Iterable[str] | None = None) -> dict[str, Any]:
		return {
			"attributes": [attr.as_dict(exclude_fields=exclude_attribute_fields) for attr in self.attributes],
		}


def get_selected_timezone() -> tzinfo | None:
	if not config.timezone:
		return None
	try:
		return zoneinfo.ZoneInfo(config.timezone)
	except Exception as exc:
		match = re.match(r"^([+-])(\d{2}):(\d{2})$", config.timezone)
		if not match:
			raise ValueError(f"Invalid timezone: '{config.timezone}'") from exc

		hours = int(match.group(2))
		minutes = int(match.group(3))
		if hours > 23 or minutes > 59:
			raise ValueError(f"Invalid timezone: '{config.timezone}'") from exc

		offset = timedelta(hours=hours, minutes=minutes)
		if match.group(1) == "-":
			offset = -offset
		return timezone(offset, name=config.timezone)


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


@contextmanager
def get_progress() -> Generator[Progress]:
	with Progress(console=get_console(output_type=OutputType.PROGRESS)) as progress:
		yield progress


def get_console(*, output_type: OutputType, file: IO[str] | None = None) -> Console:
	"""
	Get a console instance.
	:param output_type: The type of output (message, warning_message, error_message, progress, prompt, data)
	:param file: The file to write to. default:
		sys.stdout for prompt and data
		sys.stderr for message, warning_message, error_message and progress
	"""
	if not file:
		file = sys.stdout if output_type == OutputType.DATA else sys.stderr

	cls = Console
	if (output_type in (OutputType.WARNING_MESSAGE, OutputType.ERROR_MESSAGE) and config.hide_errors) or (
		output_type not in (OutputType.WARNING_MESSAGE, OutputType.ERROR_MESSAGE, OutputType.DATA, OutputType.PROMPT) and config.quiet
	):
		cls = QuietConsole
	return cls(file=file, color_system="auto" if config.color else None)


def console_print(
	*args: Any,
	rule: str | None = None,
	style: str | None = None,
	file: IO[str] | None = None,
	output_type: OutputType = OutputType.MESSAGE,
	**kwargs: Any,
) -> None:
	"""
	Print to console.
	:param args: The arguments to print
	:param rule: The rule to print
	:param style: The style to use. default:
		"yellow" for warning_message
		"red" for error_message
	:param file: The file to write to. default:
		sys.stdout for prompt and data
		sys.stderr for message, warning_message, error_message and progress
	:param output_type: The type of output (message, warning_message, error_message, progress, prompt, data)
	:param kwargs: The keyword arguments to pass to the print or rule function
	"""
	if not style and (not args or not isinstance(args[0], Text)):
		if output_type == OutputType.WARNING_MESSAGE:
			style = "yellow"
		elif output_type == OutputType.ERROR_MESSAGE:
			style = "red"

	console = get_console(output_type=output_type, file=file)
	if rule:
		console.rule(rule, **kwargs)
	else:
		console.print(*args, style=style, **kwargs)


def deprecation_warning(message: str) -> None:
	"""
	Log a deprecation warning and print it to the console.
	:param message: The message to print
	"""
	logger.warning(message)
	console_print(message, output_type=OutputType.WARNING_MESSAGE)


def prompt(
	text: str,
	return_type: type = str,
	password: bool = False,
	default: Any = ...,
	choices: list[str] | None = None,
	show_default: bool = True,
	show_choices: bool = True,
) -> str | int | float:
	"""
	Prompt the user for input.
	:param text: The text to display
	:param return_type: The type of input to return. default: str
	:param password: If True, hide the input
	:param default: The default value to return if the user does not enter anything
	:param choices: The list of choices to display
	:param show_default: If True, show the default value in the prompt
	:param show_choices: If True, show the choices in the prompt
	:return: The input from the user
	"""
	cls: type[Prompt | IntPrompt | FloatPrompt] = Prompt
	if return_type is int:
		cls = IntPrompt
	elif return_type is float:
		cls = FloatPrompt
	return cls.ask(
		prompt=text,
		console=get_console(output_type=OutputType.PROMPT),
		default=default,
		password=password,
		choices=choices,
		show_default=show_default,
		show_choices=show_choices,
	)


def to_string(
	value: Any,
	*,
	null_format: Literal["empty_string", "<null>"] = "empty_string",
	bool_format: Literal["true_false", "true_false_symbols", "1_0"] = "true_false",
	list_format: Literal["comma_space_separated", "comma_separated", "square_brackets"] = "comma_space_separated",
	value_styles: dict[str, str] | None = None,
) -> str:
	if value is None:
		value = "" if null_format == "empty_string" else "<null>"
	elif isinstance(value, bool):
		if bool_format == "true_false":
			value = "true" if value else "false"
		elif bool_format == "true_false_symbols":
			value = "✓ true" if value else "✗ false"
		else:
			value = "1" if value else "0"
	elif isinstance(value, datetime):
		# Return converted to local timezone as ISO formatted datetime string
		value = value.astimezone(tz=get_selected_timezone()).isoformat()
	elif isinstance(value, (list, tuple)):
		sep = "," if list_format == "comma_separated" else ", "
		val = sep.join(
			[
				to_string(v, null_format=null_format, bool_format=bool_format, list_format=list_format, value_styles=value_styles)
				for v in value
			]
		)
		if list_format == "square_brackets":
			return f"[{val}]"
		return val
	elif inspect.isclass(value):
		value = value.__name__

	value = str(value)
	if style := (DEFAULT_VALUE_STYLES | (value_styles or {})).get(value):
		value = f"[{style}]{value}[/{style}]"
	return value


def get_selected_attributes(
	*,
	attributes: list[Attribute] | None = None,
	fallback_attributes: Iterable[str] | None = None,
	add_identifier: bool = False,
	add_attributes: Iterable[str] | None = None,
	update_selected: bool = False,
) -> list[str]:
	"""
	Get the selected attributes based on the config and metadata.
	:param attributes: The list of available attributes from metadata.
	:param fallback_attributes: The list of attributes to use if no attributes are selected in the config.
	:param add_identifier: If True, add the identifier attributes to the selected attributes.
	:param add_attributes: The list of attributes to add to the selected attributes.
	:param update_selected: If True, update the selected state of the attributes in the config.
	"""
	selected_attributes: list[str] = []
	available_attributes = [attr.id for attr in attributes] if attributes else []
	available_attributes_set = set(available_attributes)

	def add_attribute(attribute: str) -> None:
		if attribute not in selected_attributes:
			selected_attributes.append(attribute)

	if config.attributes:
		for attr in config.attributes:
			if attr == "all":
				for available_attribute in available_attributes:
					add_attribute(available_attribute)
			else:
				if not available_attributes_set or attr in available_attributes_set:
					add_attribute(attr)
	elif fallback_attributes:
		for attr in fallback_attributes:
			if not available_attributes_set or attr in available_attributes_set:
				add_attribute(attr)
	elif attributes:
		selected_attributes = [attribute.id for attribute in attributes if attribute.selected]

	if add_identifier and attributes:
		for attr in attributes:
			if attr.identifier:
				add_attribute(attr.id)

	for attr in add_attributes or []:
		if not available_attributes_set or attr in available_attributes_set:
			add_attribute(attr)

	if update_selected:
		config.attributes = selected_attributes

	return selected_attributes


def write_output_table(data: Any, metadata: Metadata, value_styles: dict[str, str] | None = None) -> None:
	attributes = config.attributes or []
	table = Table(box=box.ROUNDED, show_header=config.header, show_lines=False)
	row_ids = []
	for attribute in metadata.attributes:
		if attributes == ["all"] or attribute.id in attributes or (not attributes and attribute.selected):
			style = "cyan" if attribute.identifier else attribute.column_style
			no_wrap = bool(attribute.identifier)
			table.add_column(header=attribute.id, style=style, no_wrap=no_wrap)
			row_ids.append(attribute.id)

	if data:
		row_type = type(data[0])
		for row in data:
			if is_dataclass(row):
				row = asdict(row)
				row_type = dict
			if issubclass(row_type, dict):
				table.add_row(*[to_string(row.get(rid), bool_format="true_false_symbols", value_styles=value_styles) for rid in row_ids])
			elif issubclass(row_type, list):
				table.add_row(*[to_string(el, bool_format="true_false_symbols", value_styles=value_styles) for el in row])
			else:
				table.add_row(*[to_string(row, bool_format="true_false_symbols", value_styles=value_styles)])
	with output_file_str() as file:
		console = get_console(output_type=OutputType.DATA, file=file)
		console.print(table)


def write_output_key_value(data: Any, metadata: Metadata, value_styles: dict[str, str] | None = None) -> None:
	attributes = config.attributes or []
	row_ids: list[str] = []
	for attribute in metadata.attributes:
		if attributes == ["all"] or attribute.id in attributes or (not attributes and attribute.selected):
			row_ids.append(attribute.id)

	lines: list[str] = []
	for ridx, row in enumerate(data):
		if is_dataclass(row):
			row = asdict(row)
		if isinstance(row, dict):
			for rid in row_ids:
				lines.append(f"[bold]{rid}[/bold]: {to_string(row.get(rid), value_styles=value_styles)}")
		elif isinstance(row, list):
			for idx, rid in enumerate(row_ids):
				value = row[idx] if idx < len(row) else None
				lines.append(f"[bold]{rid}[/bold]: {to_string(value, value_styles=value_styles)}")
		else:
			rid = row_ids[0] if row_ids else "value0"
			lines.append(f"[bold]{rid}[/bold]: {to_string(row, value_styles=value_styles)}")

		if ridx != len(data) - 1:
			lines.append("")

	output = "\n".join(lines)

	with output_file_str() as file:
		console = get_console(output_type=OutputType.DATA, file=file)
		console.print(output, highlight=False)


def write_output_csv(data: Any, metadata: Metadata) -> None:
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
			if is_dataclass(row):
				row = asdict(row)
			if isinstance(row, dict):
				writer.writerow(
					[to_string(row.get(rid), null_format="<null>", bool_format="1_0", list_format="comma_separated") for rid in row_ids]
				)
			elif isinstance(row, list):
				writer.writerow([to_string(el, null_format="<null>", bool_format="1_0", list_format="comma_separated") for el in row])
			else:
				writer.writerow([to_string(row, null_format="<null>", bool_format="1_0", list_format="comma_separated")])


def write_output_json(data: Any, metadata: Metadata | None = None, pretty: bool = False, force_newline: bool = False) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	if metadata and metadata.attributes and config.attributes and config.attributes != ["all"]:
		metadata = deepcopy(metadata)
		metadata.attributes = [attr for attr in metadata.attributes if attr.id in config.attributes]
		attributes = {attr.id for attr in metadata.attributes}
		data = [{attr: value for attr, value in row.items() if attr in attributes} for row in data]

	json = orjson.dumps(
		{"metadata": metadata.as_dict(exclude_attribute_fields=("column_style", "value_style", "validator")), "data": data}
		if config.metadata and metadata
		else data,
		default=to_string,
		option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2 if pretty and not output_file_is_a_tty() else 0,
	)

	if pretty and output_file_is_a_tty():
		print_json(json.decode("utf-8"), highlight=config.color)
	else:
		with output_file_bin() as file:
			file.write(json)
			if force_newline:
				file.write(b"\n")


def write_output_msgpack(data: Any, metadata: Metadata | None = None) -> None:
	def to_string(value: Any) -> str:
		if inspect.isclass(value):
			return value.__name__
		return str(value)

	with output_file_bin() as file:
		file.write(
			msgpack.dumps(
				{"metadata": metadata.as_dict(exclude_attribute_fields=("column_style", "value_style", "validator")), "data": data}
				if config.metadata and metadata
				else data,
				default=to_string,
			)
		)


def write_output(
	data: Any,
	metadata: Metadata | None = None,
	default_output_format: OutputFormat | None = None,
	value_styles: dict[str, str] | None = None,
	force_newline: bool = False,
) -> None:
	if output_file_is_stdout() and config.quiet:
		logger.debug("Quiet mode enabled, skipping output")
		return

	if isinstance(default_output_format, str):
		default_output_format = OutputFormat(default_output_format)

	output_format = config.output_format
	if output_format == OutputFormat.AUTO:
		output_format = default_output_format if default_output_format else OutputFormat.TABLE

	if output_format in (OutputFormat.TABLE, OutputFormat.CSV, OutputFormat.KEY_VALUE):
		stt = get_structure_type(data)
		if stt is dict:
			data = [data]
			stt = list[dict]
		if not metadata:
			if stt is list:
				metadata = Metadata(attributes=[Attribute(id="value0")])
			elif stt == list[list]:
				metadata = Metadata(attributes=[Attribute(id=f"value{idx}") for idx in range(len(data[0]))])
			elif stt == list[dict]:
				metadata = Metadata(attributes=[Attribute(id=key) for key in get_attributes(data)])
			else:
				raise RuntimeError(f"Output-format {output_format!r} does not support structure {stt!r}")

	if metadata is not None and config.attributes and config.attributes != ["all"]:
		ordered_list = [attr for config_attribute in config.attributes for attr in metadata.attributes if attr.id == config_attribute]
		remaining_list = [attr for attr in metadata.attributes if attr.id not in config.attributes]
		metadata.attributes = ordered_list + remaining_list

	if config.sort_by:
		data = sort_data(data)

	if config.limit is not None and isinstance(data, list):
		data = data[: config.limit]

	if output_format == OutputFormat.TABLE:
		assert metadata
		write_output_table(data, metadata, value_styles)
	elif output_format == OutputFormat.CSV:
		assert metadata
		write_output_csv(data, metadata)
	elif output_format == OutputFormat.KEY_VALUE:
		assert metadata
		write_output_key_value(data, metadata, value_styles)
	elif output_format in (OutputFormat.JSON, OutputFormat.PRETTY_JSON):
		write_output_json(data, metadata, output_format == OutputFormat.PRETTY_JSON, force_newline=force_newline)
	elif output_format == OutputFormat.MSGPACK:
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
				row[cidx] = None  # ty: ignore[invalid-assignment]
		if row:
			if header:
				rows.append({header[i]: row[i] for i in range(len(header))})
			else:
				rows.append(row)
	return rows


def read_input_key_value(data: bytes) -> list[dict[str, str]]:
	rows: list[dict[str, str]] = []
	current_row: dict[str, str] = {}
	for line in data.decode("utf-8").split("\n"):
		if not line.strip():
			if current_row:
				rows.append(current_row)
				current_row = {}
			continue
		if ":" not in line:
			continue
		key, value = line.split(":", 1)
		current_row[key.strip()] = value.strip()
	if current_row:
		rows.append(current_row)
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
			if data.count(b";") > data.count(b":"):
				logger.debug("Trying csv")
				return read_input_csv(data)
			else:
				logger.debug("Trying key-value")
				return read_input_key_value(data)


def list_attributes(metadata: Metadata) -> None:
	attributes_metadata = Metadata(
		attributes=[
			Attribute(id="id", description="Attribute ID", identifier=True, data_type="str"),
			Attribute(id="description", description="Description of the attribute", data_type="str"),
			Attribute(id="type", description="Data type", data_type="str"),
			Attribute(id="identifier", description="If the attribute is an identifier", data_type="bool"),
			Attribute(id="selected", description="If the attribute is selected by default", data_type="bool"),
		]
	)
	attributes_data = [
		{
			"id": attribute.id,
			"type": attribute.data_type,
			"description": attribute.description,
			"identifier": attribute.identifier,
			"selected": attribute.selected,
		}
		for attribute in metadata.attributes
	]
	write_output(attributes_data, metadata=attributes_metadata, default_output_format=OutputFormat.TABLE)


def get_editor() -> list[str]:
	if config.editor:
		return shlex.split(config.editor)
	if is_windows():
		return ["notepad"]
	return shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or shutil.which("editor") or "vi")


def get_separated_entries(value: str | None) -> list[str]:
	if value is None:
		return []
	separator = config.input_separator
	return [entry.strip() for entry in value.split(separator) if entry.strip()]
