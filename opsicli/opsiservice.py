# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

opsi service
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from opsicommon.client.jsonrpc import JSONRPCClient  # type: ignore[import]
from opsicommon.logging import logger, secret_filter  # type: ignore[import]

from opsicli import __version__
from opsicli.cache import cache
from opsicli.config import config

jsonrpc_client = None  # pylint: disable=invalid-name


def get_service_credentials_from_backend() -> Tuple[str, str]:
	dispatch_conf = Path("/etc/opsi/backendManager/dispatch.conf")
	backend = "mysql"
	for line in dispatch_conf.read_text(encoding="utf-8").splitlines():
		match = re.search(r"backend_.*:\s*(\S+)", line)  # pylint: disable=dotted-import-in-loop
		if match:
			backend = match.group(1).replace(",", "").strip()

	if backend == "mysql":
		mysql_conf = Path("/etc/opsi/backends/mysql.conf")
		loc: Dict[str, Any] = {}
		exec(compile(mysql_conf.read_bytes(), "<string>", "exec"), None, loc)  # pylint: disable=exec-used
		cfg = loc["config"]
		with subprocess.Popen(
			[
				"mysql",
				"--defaults-file=/dev/stdin",
				"--skip-column-names",
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
	else:
		for file in Path("/var/lib/opsi/config/depots").glob("*.ini"):
			depot_id = file.stem.lower()
			for line in Path("/etc/opsi/pckeys").read_text(encoding="utf-8").splitlines():
				if line and line.strip() and ":" in line:
					host_id, host_key = line.strip().split(":")
					if host_id.lower() == depot_id:
						return depot_id, host_key.strip()

	raise RuntimeError("Failed to get service credentials")


def get_service_connection() -> JSONRPCClient:
	global jsonrpc_client  # pylint: disable=invalid-name,global-statement
	if not jsonrpc_client:
		address = config.service
		username = config.username
		password = config.password
		for service in config.services:
			if service.name == config.service:
				address = service.url
				if service.username:
					username = service.username
				if service.password:
					password = service.password

		if not username or not password and urlparse(address).hostname in ("localhost", "::1", "127.0.0.1"):
			try:
				username, password = get_service_credentials_from_backend()
			except Exception as err:  # pylint: disable=broad-except
				logger.warning(err)

		session_lifetime = 15
		cache_key = f"jsonrpc-session-{address}-{username}"
		session_id = cache.get(cache_key)
		if session_id:
			secret_filter.add_secrets(session_id.split("=", 1)[1])
			logger.debug("Reusing session %s", session_id)
		jsonrpc_client = JSONRPCClient(
			address=address,
			username=username,
			password=password,
			application=f"opsi-cli/{__version__}",
			session_lifetime=session_lifetime,
			session_id=session_id,
		)
		cache.set(cache_key, jsonrpc_client.session_id, ttl=session_lifetime)
	return jsonrpc_client
