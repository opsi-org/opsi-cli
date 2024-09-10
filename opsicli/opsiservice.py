# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

opsi service
"""

from urllib.parse import urlparse

from opsicommon.client.opsiservice import (
	OpsiServiceVerificationError,
	ServiceClient,
	ServiceConnectionListener,
	get_service_client,
)
from opsicommon.logging import get_logger
from opsicommon.objects import OpsiDepotserver

from opsicli import __version__
from opsicli.cache import cache
from opsicli.config import config
from opsicli.io import prompt

logger = get_logger("opsicli")
service_client = None
SESSION_LIFETIME = 150  # seconds


class OpsiCliConnectionListener(ServiceConnectionListener):
	def connection_established(self, service_client: ServiceClient) -> None:
		logger.trace("Connection has been established, cookies: %s", service_client._session.cookies)
		session_cookie = service_client._session.cookies.get_dict().get("opsiconfd-session")  # type: ignore[no-untyped-call]
		if session_cookie:
			cache.set("opsiconfd-session", f"opsiconfd-session={session_cookie}", SESSION_LIFETIME - 10)


def get_depot_connection(depot: OpsiDepotserver) -> ServiceClient:
	"""
	Returns a connection to the depot.
	"""
	url = urlparse(depot.repositoryRemoteUrl)
	hostname = url.hostname

	if hostname is None:
		raise ValueError("Hostname could not be parsed from the repository URL.")

	if isinstance(hostname, bytes):
		hostname = hostname.decode("utf-8")

	if ":" in hostname:  # IPv6 address
		hostname = f"[{hostname}]"

	connection = get_service_client(
		address=f"https://{hostname}:{url.port or 4447}",
		username=depot.id,
		password=depot.opsiHostKey,
		user_agent=f"opsi-cli/{__version__}",
		jsonrpc_create_methods=False,
		jsonrpc_create_objects=False,
	)
	return connection


def get_service_connection() -> ServiceClient:
	global service_client
	if not service_client:
		address: str | None = None
		username: str | None = None
		password: str | None = None

		if config.service:
			service_conf = config.get_service_by_name(config.service)
			if service_conf:
				address = service_conf.url
				username = service_conf.username
				password = service_conf.password
			else:
				address = config.service
		if config.username:
			username = config.username
		if config.password:
			password = config.password

		totp = str(prompt("Enter the TOTP", password=True)) if config.totp else None

		if username and not password and config.interactive:
			password = str(prompt(f"Please enter the password for {username}@{address}", password=True))

		session_cookie = cache.get("opsiconfd-session")  # None if previous session expired
		if session_cookie:
			logger.info("Reusing session cookie from cache")

		service_client = get_service_client(
			address=address,
			username=username,
			password=password,
			totp=totp,
			user_agent=f"opsi-cli/{__version__}",
			session_lifetime=SESSION_LIFETIME,
			session_cookie=session_cookie,
			jsonrpc_create_methods=True,
			jsonrpc_create_objects=True,
			auto_connect=False,
		)
		service_client.register_connection_listener(OpsiCliConnectionListener())
		try:
			service_client.connect()
		except OpsiServiceVerificationError as err:
			if service_client.ca_cert_file and service_client.ca_cert_file.exists():
				raise OpsiServiceVerificationError(
					f"{err}. Please check or remove the certificate file '{service_client.ca_cert_file}'"
				) from err
			raise

	return service_client
