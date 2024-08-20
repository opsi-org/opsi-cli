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

	def wait_for_hosts(self, hosts: set[str], timeout: float | None = None) -> tuple[dict[str, str | None], dict[str, str | None]]:
		logger.notice("Waiting for %d hosts to connect", len(hosts))
		succeeded: dict[str, str | None] = {}
		failed: dict[str, str | None] = {}
		try:
			self.waiting_for_hosts = hosts.copy()
			with self.connection():
				self.subscribe_to_channel("event:host_connected")

				for host_id in self.service_client.jsonrpc("host_getMessagebusConnectedIds"):
					if host_id in self.waiting_for_hosts:
						logger.info("Host %s already connected", host_id)
						self.waiting_for_hosts.remove(host_id)

				if self.waiting_for_hosts:
					self.hosts_found_event.wait(timeout)

				succeeded = {host_id: None for host_id in hosts if host_id not in self.waiting_for_hosts}
				failed = {host_id: "Host did not connect in time" for host_id in self.waiting_for_hosts}

				if not failed:
					logger.notice("All hosts are connected")
				else:
					logger.error("Only %d of %d hosts connected after timeout %s", len(succeeded), len(hosts), timeout)
					for client in failed:
						logger.info("Host %s did not connect in time", client)
		finally:
			self.waiting_for_hosts = set()
			self.hosts_found_event.clear()

		return succeeded, failed


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

	def trigger_event_on_clients(self, event: str, clients: set[str]) -> tuple[dict[str, str | None], dict[str, str | None]]:
		logger.notice("Triggering event %r on clients %s", event, clients)
		if config.dry_run or not clients:
			return ({c: None for c in clients}, {})

		result = self.service.jsonrpc("hostControl_fireEvent", [event, clients])
		return evaluate_rpc_dict_result(result)

	def _wakeup_clients(self, clients: set[str], wakeup_timeout: float = 0) -> tuple[dict[str, str | None], dict[str, str | None]]:
		logger.notice("Waking up clients %s", clients)
		if config.dry_run or not clients:
			return ({c: None for c in clients}, {})

		result = self.service.jsonrpc("hostControl_start", [clients])
		# "result": "sent" in case of successfully sent (but no control over if the package reaches its destination!)
		succeeded, failed = evaluate_rpc_dict_result(result, log_success=False)

		logger.notice("Sent wakeup package to %d of %d clients", len(succeeded), len(clients))

		if wakeup_timeout <= 0:
			return succeeded, failed

		mbus_connection = WaitForHostsMessagebusConnection()
		return mbus_connection.wait_for_hosts(clients, timeout=wakeup_timeout)

	def trigger_event(self, event: str = "on_demand", wakeup: bool = False, wakeup_timeout: float = 60.0) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		reachable_clients, unreachable_clients = self.divide_clients_by_reachable()
		errors = []

		if unreachable_clients:
			if wakeup:
				failed = self._wakeup_clients(unreachable_clients, wakeup_timeout=wakeup_timeout)[1]
				if failed:
					err = "\n".join(f"{client}: {error}" for client, error in failed.items())
					msg = f"Failed to wake up {len(failed)} clients:\n{err}"
					logger.error(msg)
					errors.append(msg)
				else:
					logger.notice("Successfully woke up all not reachable clients")
				reachable_clients, unreachable_clients = self.divide_clients_by_reachable()
			else:
				err = "\n".join(unreachable_clients)
				msg = f"Could not reach {len(unreachable_clients)} clients:\n{err}"
				logger.error(msg)
				errors.append(msg)

		client_count = len(reachable_clients)

		if reachable_clients:
			failed = self.trigger_event_on_clients(event, reachable_clients)[1]
			if failed:
				err = "\n".join(f"{client}: {error}" for client, error in failed.items())
				msg = f"Failed to trigger event on {len(failed)} of {client_count} reachable clients:\n{err}"
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
		failed = evaluate_rpc_dict_result(result)[1]

		if not failed:
			msg = f"Successfully shutdown {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		err = "\n".join(f"{client}: {error}" for client, error in failed.items())
		raise RuntimeError(f"Failed to shutdown {len(failed)} of {client_count} clients:\n{err}")

	def wakeup_clients(self, wakeup_timeout: float = 0) -> None:
		if not self.clients:
			return

		client_count = len(self.clients)

		if config.dry_run:
			msg = f"Operating in dry-run mode - would wake {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		failed = self._wakeup_clients(self.clients, wakeup_timeout=wakeup_timeout)[1]

		if not failed:
			msg = f"Successfully woke {client_count} clients"
			logger.notice(msg)
			get_console().print(msg)
			return

		err = "\n".join(f"{client}: {error}" for client, error in failed.items())
		raise RuntimeError(f"Failed to wake {len(failed)} of {client_count} clients:\n{err}")
