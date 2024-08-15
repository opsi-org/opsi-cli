"""
opsi-cli basic command line interface for opsi

trigger_event_worker
"""

from threading import Event

from opsicommon.logging import get_logger
from opsicommon.messagebus.message import EventMessage

from opsicli.config import config
from opsicli.io import get_console
from opsicli.messagebus import MessagebusConnection
from opsicli.utils import evaluate_rpc_dict_result

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")


class WaitForHostsMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.waiting_for_hosts: set[str] = set()
		self.hosts_found_event = Event()

	def _on_event(self, message: EventMessage) -> None:
		if message.event != "host_connected":
			return
		logger.info("Host %s connected to messagebus", message.data["host"]["id"])
		if message.data["host"]["id"] in self.waiting_for_hosts:
			self.waiting_for_hosts.remove(message.data["host"]["id"])
		if not self.waiting_for_hosts:
			self.hosts_found_event.set()

	def wait_for_hosts(self, hosts: set[str], timeout: float | None = None) -> int:
		logger.notice("Waiting for %d hosts to connect", len(hosts))
		try:
			self.waiting_for_hosts = hosts.copy()
			with self.connection():
				self.subscribe_to_channel("event:host_connected")

				for host_id in self.service_client.jsonrpc("host_getMessagebusConnectedIds"):
					if host_id in self.waiting_for_hosts:
						logger.info("Host %s already connected", host_id)
						self.waiting_for_hosts.remove(host_id)

				if not self.waiting_for_hosts or self.hosts_found_event.wait(timeout):
					logger.notice("All hosts are connected")
					return len(hosts)

				not_reached = self.waiting_for_hosts.copy()
				logger.error(
					"Only %s of %s hosts connected after timeout %s",
					len(hosts) - len(not_reached),
					len(hosts),
					timeout,
				)
				for client in not_reached:
					logger.info("Host %s did not connect in time", client)
				return len(hosts) - len(not_reached)
		finally:
			self.waiting_for_hosts = set()
			self.hosts_found_event.clear()


class HostControlWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args, default_all=False, error_if_no_clients_online=False)

	def divide_clients_by_reachable(self) -> tuple[set[str], set[str]]:
		all_reachable = set(self.service.jsonrpc("host_getMessagebusConnectedIds"))
		selected_reachable = self.clients.intersection(all_reachable)
		selected_unreachable = self.clients - selected_reachable
		logger.info("Number of reachable selected clients: %s", len(selected_reachable))
		logger.info("Number of not reachable selected clients: %s", len(selected_unreachable))
		return selected_reachable, selected_unreachable

	def trigger_event_on_clients(self, event: str, clients: set[str]) -> int:
		logger.notice("Triggering event %r on clients %s", event, clients)
		if config.dry_run or not clients:
			return len(clients)

		result = self.service.jsonrpc("hostControl_fireEvent", [event, clients])
		return evaluate_rpc_dict_result(result)

	def _wakeup_clients(self, clients: set[str], wakeup_timeout: float = 0) -> int:
		logger.notice("Waking up clients %s", clients)
		if config.dry_run or not clients:
			return len(clients)

		result = self.service.jsonrpc("hostControl_start", [clients])
		# "result": "sent" in case of successfully sent (but no control over if the package reaches its destination!)
		success_count = evaluate_rpc_dict_result(result, log_success=False)

		logger.notice("Sent wakeup package to %s of %s clients", success_count, len(clients))

		if wakeup_timeout <= 0:
			return success_count

		mbus_connection = WaitForHostsMessagebusConnection()
		return mbus_connection.wait_for_hosts(clients, timeout=wakeup_timeout)

	def trigger_event(self, event: str = "on_demand", wakeup: bool = False, wakeup_timeout: float = 60.0) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		reachable_clients, unreachable_clients = self.divide_clients_by_reachable()

		errors = []

		if unreachable_clients:
			if wakeup:
				self._wakeup_clients(unreachable_clients, wakeup_timeout=wakeup_timeout)
				reachable_clients, unreachable_clients = self.divide_clients_by_reachable()
				if unreachable_clients:
					msg = f"Failed to wake up {len(unreachable_clients)} clients"
					logger.error(msg)
					errors.append(msg)
				else:
					logger.notice("Successfully woke up all not reachable clients")
			else:
				msg = f"Could not reach {len(unreachable_clients)} clients"
				logger.error(msg)
				errors.append(msg)

		client_count = len(reachable_clients)

		if reachable_clients:
			success_count = self.trigger_event_on_clients(event, reachable_clients)
			if success_count != client_count:
				msg = f"Failed to trigger event on {client_count - success_count} of {client_count} reachable clients"
				logger.error(msg)
				errors.append(msg)

		msg = f"Successfully triggered event on {client_count} clients"
		logger.notice(msg)
		get_console().print(msg)

		if errors:
			raise RuntimeError("\n".join(errors))

	def shutdown_clients(self) -> None:
		if not self.clients:
			return

		client_count = len(self.clients)

		if config.dry_run:
			msg = f"Operating in dry-run mode - would shutdown {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		logger.notice("Shutting down clients %s", self.clients)
		result = self.service.jsonrpc("hostControl_shutdown", [self.clients])
		success_count = evaluate_rpc_dict_result(result)

		if success_count == client_count:
			msg = f"Successfully shutdown {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		raise RuntimeError(f"Failed to shutdown {client_count - success_count} of {client_count} clients")

	def wakeup_clients(self, wakeup_timeout: float = 0) -> None:
		if not self.clients:
			return

		client_count = len(self.clients)

		if config.dry_run:
			msg = f"Operating in dry-run mode - would wake {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		success_count = self._wakeup_clients(self.clients, wakeup_timeout=wakeup_timeout)

		if success_count == client_count:
			msg = f"Successfully woke {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		raise RuntimeError(f"Failed to wake {client_count - success_count} of {client_count} clients")
