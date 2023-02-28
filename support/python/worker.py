"""
worker functions needed by opsi-cli support plugin
"""

from typing import Any

from opsicli.io import Attribute, Metadata
from opsicli.opsiservice import get_service_connection


def default_health_check() -> tuple[list[dict[str, Any]], Metadata]:
	service_data = get_service_connection().jsonrpc("service_healthCheck")

	metadata = Metadata(
		attributes=[
			Attribute(id="name", description=""),
			Attribute(id="id", description=""),
			Attribute(id="description", description=""),
			Attribute(id="status", description=""),
			Attribute(id="message", description=""),
			Attribute(id="partial_results", description=""),
			Attribute(id="partial_results_status", description=""),
			Attribute(id="partial_results_message", description=""),
			Attribute(id="upgrade_issue", description=""),
		],
	)
	data = []
	for i in service_data:
		data.append(
			{
				"name": i["check_name"],
				"id": i["check_id"],
				"description": i["check_description"],
				"status": i["check_status"],
				"message": i["message"],
				"err_status": i["check_status"],
				"upgrade_issue": i["upgrade_issue"],
			}
		)
		for result in i["partial_results"]:
			data.append(
				{
					"partial_results": result["check_id"],
					"partial_results_status": result["check_status"],
					"partial_results_message": result["message"],
					"err_status": result["check_status"],
				}
			)
	return data, metadata
