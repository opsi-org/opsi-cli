# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

opsi service
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opsicommon.client.opsiservice import ServiceClient, ServiceConnectionListener, ServiceVerificationFlags
from opsicommon.config import OpsiConfig
from opsicommon.logging import get_logger, secret_filter

from opsicli import __version__
from opsicli.cache import cache
from opsicli.config import config
from opsicli.io import prompt

logger = get_logger("opsicli")
jsonrpc_client = None
SESSION_LIFETIME = 15  # seconds


class OpsiCliConnectionListener(ServiceConnectionListener):
	def connection_established(self, service_client: ServiceClient) -> None:
		logger.trace("Connection has been established, cookies: %s", service_client._session.cookies)
		session_cookie = service_client._session.cookies.get_dict().get("opsiconfd-session")  # type: ignore[no-untyped-call]
		if session_cookie:
			cache.set("opsiconfd-session", f"opsiconfd-session={session_cookie}", SESSION_LIFETIME)


def get_service_credentials_from_backend() -> tuple[str, str]:
	logger.info("Fetching credentials from backend")
	dispatch_conf = Path("/etc/opsi/backendManager/dispatch.conf")
	backend = "mysql"
	backend_pattern = re.compile(r"backend_.*:\s*(\S+)")
	if dispatch_conf.exists():  # it not we are on opsi4.3 -> use mysql
		for line in dispatch_conf.read_text(encoding="utf-8").splitlines():
			match = re.search(backend_pattern, line)
			if match:
				backend = match.group(1).replace(",", "").strip()

	if backend == "file":
		for file in Path("/var/lib/opsi/config/depots").glob("*.ini"):
			depot_id = file.stem.lower()
			for line in Path("/etc/opsi/pckeys").read_text(encoding="utf-8").splitlines():
				if line and line.strip() and ":" in line:
					host_id, host_key = line.strip().split(":")
					if host_id.lower() == depot_id:
						return depot_id, host_key.strip()
	else:
		mysql_conf = Path("/etc/opsi/backends/mysql.conf")
		loc: dict[str, Any] = {}
		exec(compile(mysql_conf.read_bytes(), "<string>", "exec"), None, loc)
		cfg = loc["config"]
		with subprocess.Popen(
			[
				"mysql",
				"--defaults-file=/dev/stdin",
				"--skip-column-names",
				"-h",
				urlparse(cfg["address"]).hostname or cfg["address"],
				"-D",
				cfg["database"],
				"-e",
				"SELECT hostId, opsiHostKey FROM HOST WHERE type='OpsiConfigserver';",
			],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
		) as proc:
			out = proc.communicate(input=f"[client]\nuser={cfg['username']}\npassword={cfg['password']}\n".encode())
			if proc.returncode != 0:
				raise RuntimeError(f"mysql command failed ({proc.returncode}): {out[1].decode()}")
			res = out[0].decode().strip()
			if res:
				host_id, host_key = res.split()
				return host_id, host_key

	raise RuntimeError("Failed to get service credentials")


def get_opsiconfd_config() -> dict[str, str]:
	config = {"ssl_server_key": "", "ssl_server_cert": "", "ssl_server_key_passphrase": ""}
	try:
		proc = subprocess.run(["opsiconfd", "get-config"], shell=False, check=True, capture_output=True, text=True, encoding="utf-8")
		for attr, value in json.loads(proc.stdout).items():
			if attr in config.keys() and value is not None:
				config[attr] = value
				if attr == "ssl_server_key_passphrase":
					secret_filter.add_secrets(value)
	except Exception as err:
		logger.debug("Failed to get opsiconfd config %s", err)
	return config


def get_service_connection() -> ServiceClient:
	global jsonrpc_client
	if not jsonrpc_client:
		address = config.service
		username = config.username
		password = config.password
		client_cert_file = None
		client_key_file = None
		client_key_password = None
		service = config.get_service_by_name(config.service)

		if service:
			address = service.url
			if service.username:
				username = service.username
			if service.password:
				password = service.password
		else:
			opsiconf = OpsiConfig(upgrade_config=False)
			if not username or not password:
				logger.info("Fetching credentials from opsi config file")
				try:
					username = opsiconf.get("host", "id")
					password = opsiconf.get("host", "key")
					cfg = get_opsiconfd_config()
					logger.debug("opsiconfd config: %r", cfg)
					if (
						cfg["ssl_server_key"]
						and os.path.exists(cfg["ssl_server_key"])
						and cfg["ssl_server_cert"]
						and os.path.exists(cfg["ssl_server_cert"])
					):
						client_cert_file = cfg["ssl_server_cert"]
						client_key_file = cfg["ssl_server_key"]
						client_key_password = cfg["ssl_server_key_passphrase"]
				except Exception as error:
					logger.info("Failed to get credentials from opsi config file: %s", error)
			if not username or not password and urlparse(address).hostname in ("localhost", "::1", "127.0.0.1"):
				try:
					username, password = get_service_credentials_from_backend()
				except Exception as err:
					logger.warning(err)

		if username and not password and config.interactive:
			password = str(prompt(f"Please enter the password for {username}@{address}", password=True))

		jsonrpc_client = ServiceClient(
			address=address,
			username=username,
			password=password,
			user_agent=f"opsi-cli/{__version__}",
			session_lifetime=SESSION_LIFETIME,
			session_cookie=cache.get("opsiconfd-session"),  # None if previous session expired
			verify=ServiceVerificationFlags.ACCEPT_ALL,
			client_cert_file=client_cert_file,
			client_key_file=client_key_file,
			client_key_password=client_key_password,
		)
		jsonrpc_client.register_connection_listener(OpsiCliConnectionListener())

	return jsonrpc_client
