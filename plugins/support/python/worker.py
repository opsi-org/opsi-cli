"""
worker functions needed by opsi-cli support plugin
"""

from typing import Any

from opsicli.opsiservice import get_service_connection


def default_health_check() -> list[dict[str, Any]]:
	service_data = get_service_connection().jsonrpc("service_healthCheck")

	data = []
	for entry in service_data:
		data.append(
			{
				"id": entry["check_id"],
				"status": entry["check_status"],
				"message": entry["message"],
				"err_status": entry["check_status"],
			}
		)
		for result in entry["partial_results"]:
			data.append(
				{
					"partial_results": result["check_id"],
					"partial_results_status": result["check_status"],
					"partial_results_message": result["message"],
					"err_status": result["check_status"],
				}
			)
	return data
