# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

opsi service
"""

from urllib.parse import urlparse

from opsicommon.client.opsiservice import OpsiServiceVerificationError, ServiceClient, ServiceConnectionListener, get_service_client
from opsicommon.exceptions import OpsiServiceAuthenticationError
from opsicommon.logging import get_logger
from opsicommon.objects import OpsiDepotserver
from opsicommon.utils import unix_timestamp

from opsicli import __version__
from opsicli.cache import cache
from opsicli.config import config
from opsicli.io import prompt

logger = get_logger("opsicli")
service_client = None


class OpsiCliConnectionListener(ServiceConnectionListener):
	def connection_established(self, service_client: ServiceClient) -> None:
		logger.trace("Connection has been established, cookies: %s", service_client._session.cookies)
		cookies = [cookie for cookie in service_client._session.cookies if cookie.domain and cookie.name == "opsiconfd-session"]
		if not cookies:
			logger.warning("No session cookie received")
			return
		cookie = cookies[0]
		current_timestamp = unix_timestamp()
		seconds_left = round(cookie.expires or 0 - current_timestamp)
		if seconds_left <= 0:
			logger.warning("Session cookie expired")
			return
		logger.debug("Session cookie expires in %d seconds", seconds_left)
		if seconds_left > 10:
			cache.set("opsiconfd-session", f"opsiconfd-session={cookie.value}", seconds_left - 10)


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


def get_service_connection(verify: str | None = None) -> ServiceClient:
	global service_client
	if service_client:
		return service_client

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

	totp: str | None = None
	session_cookie = cache.get("opsiconfd-session")  # None if previous session expired
	if session_cookie:
		logger.info("Reusing session cookie from cache")
	elif not config.sso:
		if config.username:
			username = config.username
		if config.password:
			password = config.password

		if username and not password and config.interactive:
			password = str(prompt(f"Please enter the password for {username}@{address}", password=True))

		if config.totp:
			totp = str(prompt("Enter the TOTP", password=True))

	new_service_client = get_service_client(
		address=address,
		username=username,
		password=password,
		totp=totp,
		sso=config.sso,
		user_agent=f"opsi-cli/{__version__}",
		session_lifetime=config.session_lifetime,
		session_cookie=session_cookie,
		jsonrpc_create_methods=True,
		jsonrpc_create_objects=True,
		auto_connect=False,
		verify=verify,
	)

	new_service_client.register_connection_listener(OpsiCliConnectionListener())
	try:
		new_service_client.connect()
	except OpsiServiceAuthenticationError:
		if not session_cookie:
			raise
		logger.warning("Authentication failed with session cookie, trying again without it")
		cache.delete("opsiconfd-session", store=True)
		return get_service_connection(verify=verify)
	except OpsiServiceVerificationError as err:
		if new_service_client.ca_cert_file and new_service_client.ca_cert_file.exists():
			raise OpsiServiceVerificationError(
				f"{err}. Please check or remove the certificate file '{new_service_client.ca_cert_file}'"
			) from err
		raise

	service_client = new_service_client
	return service_client


def reset_service_connection() -> None:
	global service_client
	service_client = None
