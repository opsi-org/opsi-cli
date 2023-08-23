"""
opsi-cli basic command line interface for opsi

trigger_event_worker
"""

import time
from datetime import datetime, timedelta

from opsicommon.logging import get_logger

from opsicli.config import config

from .client_action_worker import ClientActionWorker

logger = get_logger("opsicli")

WAKEUP_TIMEOUT = 60
CONNECTION_POLL_INTERVAL = 10


def evaluate_rpc_result(result: dict[str, dict[str, str | None]], log_success: bool = True) -> int:
	num_success = 0
	for client, response in result.items():
		if response.get("error"):
			logger.warning("%s: ERROR", client)
			logger.info(response["error"])
		else:
			if log_success:
				logger.info("%s: SUCCESS", client)
			num_success += 1
	return num_success


class TriggerEventWorker(ClientActionWorker):
	def divide_clients_by_reachable(self) -> tuple[list[str], list[str]]:
		all_reachable = self.service.jsonrpc("host_getMessagebusConnectedIds")
		selected_reachable = [entry for entry in self.clients if entry in all_reachable]
		selected_unreachable = [entry for entry in self.clients if entry not in all_reachable]
		logger.info("Number of reachable selected clients: %s", len(selected_reachable))
		logger.info("Number of not reachable selected clients: %s", len(selected_unreachable))
		return selected_reachable, selected_unreachable

	def trigger_event_on_clients(self, event: str, clients: list[str]) -> int:
		logger.notice("Triggering event %r on clients %s", event, clients)
		if config.dry_run:
			return 0
		result = self.service.jsonrpc("hostControlSafe_fireEvent", [event, clients])
		return evaluate_rpc_result(result)

	def wakeup_clients(self, clients: list[str]) -> int:
		logger.notice("Waking up clients %s", clients)
		if config.dry_run:
			return 0
		result = self.service.jsonrpc("hostControlSafe_start", [clients])
		# "result": "sent" in case of successfully sent (but no control over if the package reaches its destination!)
		logger.notice(
			"Sent wakeup package to %s / %s clients - waiting for connection.",
			evaluate_rpc_result(result, log_success=False),
			len(clients),
		)
		timeout = datetime.now() + timedelta(seconds=WAKEUP_TIMEOUT)
		unreached = clients.copy()
		while datetime.now() < timeout:
			all_reachable = self.service.jsonrpc("host_getMessagebusConnectedIds")
			for client in unreached:
				if client in all_reachable:
					logger.info("%s: SUCCESS", client)
					unreached.remove(client)
			if not unreached:
				break
			time.sleep(CONNECTION_POLL_INTERVAL)
		for client in unreached:
			logger.warning("%s: ERROR", client)
		return len(clients) - len(unreached)

	def trigger_event(self, event: str = "on_demand", wakeup: bool = False) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		reachable, not_reachable = self.divide_clients_by_reachable()
		wakeup_success = 0
		event_trigger_success = 0
		if not_reachable:
			if wakeup:
				wakeup_success = self.wakeup_clients(not_reachable)
			else:
				logger.error("Could not reach %s clients: %s", len(not_reachable), not_reachable)
		if reachable:
			event_trigger_success = self.trigger_event_on_clients(event, reachable)

		if wakeup:
			if wakeup_success == len(not_reachable):
				logger.notice("Successfully woke up all not reachable clients")
			else:
				logger.error("Failed to wake up %s / %s not reachable clients", len(not_reachable) - wakeup_success, len(not_reachable))
		if event_trigger_success == len(reachable):
			logger.notice("Successfully triggered event on all reachable clients")
		else:
			logger.error("Failed to trigger event on  %s / %s reachable clients", len(reachable) - event_trigger_success, len(reachable))
