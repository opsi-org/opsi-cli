"""
worker functions needed by opsi-cli support plugin
"""

from typing import Any

from opsicli.opsiservice import get_service_connection


def status_color_id(entry: dict[str, Any]) -> str:
	if entry["check_status"] == "ok":
		return f"[green]{entry['check_id']}[/green]"
	if entry["check_status"] == "warning":
		return f"[yellow]{entry['check_id']}[/yellow]"
	return f"[red]{entry['check_id']}[/red]"


def category_health_check(category: str) -> list[dict[str, Any]]:
	service_data = get_service_connection().jsonrpc("service_healthCheck")
	data = []
	for entry in service_data:
		if not entry["check_id"] == category:
			continue
		data.append({"id": status_color_id(entry), "details": f"[bold white]{entry['message']}[/bold white]"})
		for partial in entry["partial_results"]:
			entry_dict = {"id": status_color_id(partial)}
			entry_dict["details"] = partial["message"]
			data.append(entry_dict)
		break
	return data


def default_health_check(detailed: bool = False) -> list[dict[str, Any]]:
	service_data = get_service_connection().jsonrpc("service_healthCheck")
	data = []
	for entry in service_data:
		entry_dict = {"id": status_color_id(entry)}
		problems = []
		if detailed:
			for partial in entry["partial_results"]:
				if partial["check_status"] == "warning":
					problems.append(f"[yellow]{partial['message']}[/yellow]")
				if partial["check_status"] == "error":
					problems.append(f"[red]{partial['message']}[/red]")
			if problems:
				entry_dict["details"] = "\n".join(problems)
			else:
				entry_dict["details"] = "[green]No problems detected[/green]"
		else:
			entry_dict["details"] = entry["message"]
		data.append(entry_dict)

	return data
