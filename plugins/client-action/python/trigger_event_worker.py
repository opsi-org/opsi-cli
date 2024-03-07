"""
opsi-cli basic command line interface for opsi

trigger_event_worker
"""

from threading import Event

from opsicommon.logging import get_logger
from opsicommon.messagebus import EventMessage

from opsicli.config import config
from opsicli.messagebus import MessagebusConnection
from opsicli.utils import evaluate_rpc_dict_result

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")

WAKEUP_TIMEOUT = 60.0


class WakeupHostsMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.waiting_for_hosts: set[str] = set()
		self.hosts_found_event = Event()

	# TerminalOpenEventMessage is not subclass of EventMessage!
	def _on_event(self, message: EventMessage) -> None:
		if message.event == "host_connected":
			logger.info("host %s connected to messagebus", message.data["host"]["id"])
			if message.data["host"]["id"] in self.waiting_for_hosts:
				self.waiting_for_hosts.remove(message.data["host"]["id"])
			if not self.waiting_for_hosts:
				self.hosts_found_event.set()

	def wait_for_hosts(self, hosts: set[str], timeout: float | None = None, wakeup: bool = False) -> int:
		try:
			self.waiting_for_hosts = hosts.copy()
			with self.connection():
				self.subscribe_to_channel("event:host_connected")
				if wakeup:
					result = self.service_client.jsonrpc("hostControlSafe_start", [hosts])
					# "result": "sent" in case of successfully sent (but no control over if the package reaches its destination!)
					logger.notice(
						"Sent wakeup package to %s / %s clients - waiting for connection.",
						evaluate_rpc_dict_result(result, log_success=False),
						len(hosts),
					)
				if self.hosts_found_event.wait(timeout):
					logger.notice("Reached all requested hosts")
					return len(hosts)
				not_reached = self.waiting_for_hosts.copy()
				logger.error(
					"reached only %s / %s requested hosts before timeout %s",
					len(hosts) - len(not_reached),
					len(hosts),
					timeout,
				)
				for client in not_reached:
					logger.warning("%s: ERROR Did not respond in time", client)
				return len(hosts) - len(not_reached)
		finally:
			self.waiting_for_hosts = set()
			self.hosts_found_event.clear()


class TriggerEventWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args, default_all=False)

	def divide_clients_by_reachable(self) -> tuple[set[str], set[str]]:
		all_reachable = set(self.service.jsonrpc("host_getMessagebusConnectedIds"))
		selected_reachable = self.clients.intersection(all_reachable)
		selected_unreachable = self.clients - selected_reachable
		logger.info("Number of reachable selected clients: %s", len(selected_reachable))
		logger.info("Number of not reachable selected clients: %s", len(selected_unreachable))
		return selected_reachable, selected_unreachable

	def trigger_event_on_clients(self, event: str, clients: set[str]) -> int:
		logger.notice("Triggering event %r on clients %s", event, clients)
		if config.dry_run:
			return 0
		result = self.service.jsonrpc("hostControlSafe_fireEvent", [event, clients])
		return evaluate_rpc_dict_result(result)

	def wakeup_clients(self, clients: set[str]) -> int:
		logger.notice("Waking up clients %s", clients)
		if config.dry_run:
			return 0
		mbus_connection = WakeupHostsMessagebusConnection()
		return mbus_connection.wait_for_hosts(clients, timeout=WAKEUP_TIMEOUT, wakeup=True)

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

		if not_reachable and wakeup:
			if wakeup_success == len(not_reachable):
				logger.notice("Successfully woke up all not reachable clients")
			else:
				logger.error("Failed to wake up %s / %s not reachable clients", len(not_reachable) - wakeup_success, len(not_reachable))
		if event_trigger_success == len(reachable):
			if reachable:
				logger.notice("Successfully triggered event on all reachable clients")
		else:
			logger.error("Failed to trigger event on  %s / %s reachable clients", len(reachable) - event_trigger_success, len(reachable))
