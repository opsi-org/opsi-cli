from dataclasses import dataclass

import click
from opsi.opsi.service.model.object import (
	BoolConfig,
	BoolProductProperty,
	UnicodeConfig,
	UnicodeProductProperty,
)
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

from opsicli.decorators import static_methods
from opsicli.io import Attribute


@dataclass
class Verb:
	doing: str
	done: str


OPERATION_VERB_MAP = {
	"delete": Verb(doing="Deleting", done="deleted"),
	"update": Verb(doing="Updating", done="updated"),
	"apply": Verb(doing="Applying changes to", done="changed"),
	"edit": Verb(doing="Editing", done="edited"),
	"unlock": Verb(doing="Unlocking", done="unlocked"),
}

custom_theme = Theme(
	{
		"json.key": "bold blue",
		"json.str": "bold green",
		"json.number": "bold green",
		"json.bool_true": "bold green",
		"json.bool_false": "bold red",
		"json.null": "bold green",
	}
)


def _get_formatted_value_and_object(
	value: str | list[str], obj: BoolConfig | BoolProductProperty | UnicodeConfig | UnicodeProductProperty
) -> tuple[str, str]:
	formatted_value = ", ".join(value) if isinstance(value, list) else value

	console = Console(theme=custom_theme, color_system="truecolor")
	with console.capture() as capture:
		console.print_json(data=obj.__dict__)
	ansi_json_str = capture.get()

	return (formatted_value, ansi_json_str)


class StatusTemplates:
	SUCCESS = "{action} {object_name}s was successful. Here are the {result} {object_name}s."
	DRY_RUN = "{action} {object_name}s skipped due to dry run. Here are the {object_name}s that would have been {result}:"
	NO_CHANGES = "No changes detected, no {object_name}s were updated."


class ErrorTemplates:
	NO_MATCH = "No {object_name}s found matching the filtering criteria."
	NO_INPUT = "No input data provided for updating {object_name}s. Please set --input-file."
	NO_LISTS = "Invalid format for '{attribute}': Lists are not supported for this field."
	NOT_INTERACTIVE = "Editing is not possible in non-interactive mode."
	INVALID_OPERATOR_FOR_TYPE_LIST = (
		"Invalid operator `[red bold]{operator}[/]` for lists.\n\n"
		"[bold]Option 1:[/] Use `[bold blue]=[/]` and prepend operators directly to the values.\n"
		"[bold]Option 2:[/] Use multiple `<attribute><operator><value>` statements.\n\n"
		"[bold]Examples:[/bold]\n"
		'  [dim]1. --where[/dim] [bold]"attribute[blue]=[/][green]<=[/]value[dim],[/][green]>=[/]value"[/]\n'
		'  [dim]2. --where[/dim] [bold]"attribute[green]<=[/]value"[/]  [dim]--where[/dim] [bold]"attribute[green]>=[/]value"[/]'
	)
	INVALID_CONDITION_WHERE = (
		"Invalid filter condition: `[bold red]{condition}[/]`.\n"
		"Expected format: `[bold]<attribute><operator><value>[/]`.\n"
		"Valid operators are: `[bold]=[/]`, `[bold]<[/]`, `[bold]<=[/]`, `[bold]>[/]`, `[bold]>=[/]`.\n\n"
		"{general_help}"
	)
	INVALID_CONDITION_SET = (
		"Invalid set statement: `[bold red]{assignment}[/]`.\nExpected format: `[bold]<attribute>=<value>[/]`.\n\n{general_help}"
	)
	INVALID_VALUE_WHERE = (
		"Invalid value in filter condition: '[bold]{attribute}=[red]{value}[/][/]'.\n\n"
		"The specified {attribute} was not found. Please use one or multiple of the available {attribute}'s\n"
		"listed below, or use wildcards (e.g. '{attribute}=*' or '{attribute}=*.test')\n"
		"to filter.\n\n"
		"Available {attribute}'s are:\n"
	)
	INVALID_VALUE_SET = "Invalid value in set statement: '[bold]{attribute}=[red]{value}[/][/]'.\n\n {general_help}"
	INVALID_ATTRIBUTE_WHERE = "Invalid attribute in filter condition: `[bold][red]{attr}[/red]={value}[/]`.\n\n{general_help}"
	INVALID_ATTRIBUTE_SET = "Invalid attribute in set statement: `[bold][red]{attr}[/red]={value}[/]`.\n\n{general_help}"

	MISSING_ATTRIBUTE = (
		"Incomplete filter for {operation} operation.\n\n"
		"{general_help}\n"
		"On {operation} operations, the filter must contain all identifier attributes.\n"
		"Missing required attributes: [bold red]{missing_attr_str}[/]"
	)
	MISSING_WHERE = (
		"At least one filter condition is required to prevent unintentional retrieval of large amounts of data.\n"
		"If you intentionally do not want to filter by an attribute, use: `[bold]--all[/]`.\n\n"
		"{general_help}"
	)
	MISSING_SET = "No attributes specified to update.\n\n{general_help}"
	NOT_A_SINGLE_VALUE = "Multiple values `[bold red]{value}[/]` are not allowed for the given [bold][blue]{obj_type}[/][/]:\n\n{obj}"
	NOT_A_POSSIBLE_VALUE = "Invalid value `[bold red]{value}[/]` for the given [bold][blue]{obj_type}[/][/]:\n\n{obj}"


class HelpTemplates:
	GENERAL_WHERE = (
		'Use one or more `[bold]--where "<attribute><operator><value>"[/]` options to define the filter.\n\nAvailable attributes are:\n'
	)
	GENERAL_SET = 'Use one or more `[bold]--set "<attribute>=<value>"[/]` options to define the attributes to update.\n\n'
	INPUT_SEPARATOR_DETECTED = (
		"Your input contains a comma `[bold yellow],[/]`.\n\n"
		"If this is a single value and not a list, use the `[bold yellow]--no-input-separation[/]` flag.\n"
		"To use a different list separator, set `[bold][yellow]--input-separator[/] <separator>[/]`"
	)


def _get_operation_context() -> tuple[str, str]:
	try:
		ctx = click.get_current_context()
	except RuntimeError:
		raise RuntimeError("No Click context found. Is this function called outside a command?")

	if not ctx.parent:
		raise RuntimeError("The function needs to be called within a Click sub-command.")

	object_name = ctx.parent.command.name
	command_name = ctx.command.name

	if object_name is None or command_name is None:
		raise ValueError(
			"Incomplete context data found:\n"
			f"  object_name={object_name!r}\n"
			f"  command_name={command_name!r}\n\n"
			"Verify that the Click command structure is correctly defined."
		)
	return object_name, command_name


def _get_runtime_info() -> tuple[str, str, Verb]:

	obj, cmd = _get_operation_context()
	verb = OPERATION_VERB_MAP.get(cmd, Verb(doing="Processing", done="processed"))  # Fallback

	return obj, cmd, verb


def _format_possible_values(possible_values: list[str] | None) -> str:
	if not possible_values:
		return ""
	formatted = "\n".join([f"  {val}" for val in possible_values])
	return f"\n[bold]Possible values are:[/]\n[green]{formatted}[/green]"


# lazy loading because the context does not exist until a cli command is called
class ContextHandler:
	# will be called with first access to obj/cmd/verb
	@property
	def ctx_data(self) -> tuple[str, str, Verb]:
		return _get_runtime_info()

	@property
	def obj(self) -> str:
		return self.ctx_data[0]

	@property
	def cmd(self) -> str:
		return self.ctx_data[1]

	@property
	def verb(self) -> Verb:
		return self.ctx_data[2]


ctx = ContextHandler()


@static_methods
class Status:
	def success() -> str:
		return StatusTemplates.SUCCESS.format(action=ctx.verb.doing, result=ctx.verb.done, object_name=ctx.obj)

	def dry_run() -> str:
		return StatusTemplates.DRY_RUN.format(action=ctx.verb.doing, result=ctx.verb.done, object_name=ctx.obj)

	def no_changes() -> str:
		return StatusTemplates.NO_CHANGES.format(object_name=ctx.obj)


@static_methods
class Error:
	def no_match() -> str:
		return ErrorTemplates.NO_MATCH.format(object_name=ctx.obj)

	def no_input() -> str:
		return ErrorTemplates.NO_INPUT.format(object_name=ctx.obj)

	def not_interactive() -> str:
		return ErrorTemplates.NOT_INTERACTIVE

	def no_lists(attribute: str) -> str:
		return ErrorTemplates.NO_LISTS.format(attribute=attribute)

	def invalid_operator_for_type_list(operator: str) -> str:
		return ErrorTemplates.INVALID_OPERATOR_FOR_TYPE_LIST.format(operator=operator)

	def invalid_value_where(available_values: list[str], attribute: str, value: str | list[str]) -> str:
		help_msg = ErrorTemplates.INVALID_VALUE_WHERE.format(attribute=attribute, value=value)
		for entry in available_values:
			help_msg += f"[bold cyan]  {entry}\n"
		return help_msg

	def invalid_value_set(attr: str, value: str, general_help: str) -> str:
		return ErrorTemplates.INVALID_VALUE_SET.format(attribute=attr, value=value, general_help=general_help)

	def invalid_attribute_where(attr: str, value: str, general_help: str) -> str:
		return ErrorTemplates.INVALID_ATTRIBUTE_WHERE.format(attr=attr, value=value, general_help=general_help)

	def invalid_attribute_set(attr: str, value: str, general_help: str) -> str:
		return ErrorTemplates.INVALID_ATTRIBUTE_SET.format(attr=attr, value=value, general_help=general_help)

	def invalid_condition_where(condition: str, general_help: str) -> str:
		return ErrorTemplates.INVALID_CONDITION_WHERE.format(condition=condition, general_help=general_help)

	def invalid_condition_set(assignment: str, general_help: str) -> str:
		return ErrorTemplates.INVALID_CONDITION_SET.format(assignment=assignment, general_help=general_help)

	def missing_attribute(operation: str, missing_attr_str: str, general_help: str) -> str:
		return ErrorTemplates.MISSING_ATTRIBUTE.format(operation=operation, missing_attr_str=missing_attr_str, general_help=general_help)

	def missing_where(general_help: str) -> str:
		return ErrorTemplates.MISSING_WHERE.format(general_help=general_help)

	def missing_set(general_help: str) -> str:
		return ErrorTemplates.MISSING_SET.format(general_help=general_help)

	def not_a_single_value(
		value: str | list[str],
		obj: BoolConfig | BoolProductProperty | UnicodeConfig | UnicodeProductProperty,
	) -> str:

		formatted_value, ansi_json_str = _get_formatted_value_and_object(value, obj)
		return ErrorTemplates.NOT_A_SINGLE_VALUE.format(value=formatted_value, obj_type=type(obj).__name__, obj=ansi_json_str)

	def not_a_possible_value(
		value: str | list[str],
		obj: BoolConfig | BoolProductProperty | UnicodeConfig | UnicodeProductProperty,
	) -> str:
		formatted_value, ansi_json_str = _get_formatted_value_and_object(value, obj)
		return ErrorTemplates.NOT_A_POSSIBLE_VALUE.format(value=formatted_value, obj_type=type(obj).__name__, obj=ansi_json_str)


@static_methods
class Help:
	def general_where(
		available_attributes: list[Attribute], used_attributes: list[str] | None = None, missing_attributes: list[str] | None = None
	) -> str:
		used_attributes = used_attributes or []
		missing_attributes = missing_attributes or []

		general_help = HelpTemplates.GENERAL_WHERE

		max_attr_len = max(len(attr.id) for attr in available_attributes)
		max_type_len = max(len(str(attr.data_type)) for attr in available_attributes)
		for attr in available_attributes:
			color = "white"
			if attr.id in missing_attributes:
				color = "red"
			elif attr.id in used_attributes:
				color = "green"
			elif attr.identifier:
				color = "cyan"
			type_str = f"({attr.data_type!s})".ljust(max_type_len + 2)
			general_help += f"  [bold {color}]{attr.id.ljust(max_attr_len)}[/]  {type_str}  {attr.description}\n"
		return general_help

	def general_set(available_attributes: list[Attribute]) -> str:
		general_help = HelpTemplates.GENERAL_SET
		if not available_attributes:
			return general_help

		general_help += "Available attributes are:\n"
		max_attr_len = max(len(attr.id) for attr in available_attributes)
		max_type_len = max(len(str(attr.data_type)) for attr in available_attributes)
		for attr in available_attributes:
			type_str = f"({attr.data_type!s})".ljust(max_type_len + 2)
			general_help += f"  [bold white]{attr.id.ljust(max_attr_len)}[/]  {type_str}  {attr.description}\n"
		return general_help

	def input_separator_detected() -> Panel:
		return Panel.fit(HelpTemplates.INPUT_SEPARATOR_DETECTED, title="[yellow]Hint", border_style="yellow", title_align="left")
