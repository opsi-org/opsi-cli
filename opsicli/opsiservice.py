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

from opsicommon.client.opsiservice import (  # type: ignore[import]
	ServiceClient,
	ServiceVerificationModes,
)
from opsicommon.config import OpsiConfig  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli import __version__
from opsicli.config import config

jsonrpc_client = None  # pylint: disable=invalid-name
SESSION_LIFETIME = 15  # seconds


def get_service_credentials_from_backend() -> Tuple[str, str]:
	logger.info("Fetching credentials from backend")
	dispatch_conf = Path("/etc/opsi/backendManager/dispatch.conf")
	backend = "mysql"
	backend_pattern = re.compile(r"backend_.*:\s*(\S+)")
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
		loc: Dict[str, Any] = {}
		exec(compile(mysql_conf.read_bytes(), "<string>", "exec"), None, loc)  # pylint: disable=exec-used
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


def get_service_connection() -> ServiceClient:
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

		opsiconf = OpsiConfig(upgrade_config=False)
		if not username or not password:
			logger.info("Fetching credentials from opsi config file")
			try:
				username = opsiconf.get("host", "id")
				password = opsiconf.get("host", "key")
			except Exception as error:  # pylint: disable=broad-except
				logger.info("Failed to get credentials from opsi config file: %s", error)
		if not username or not password and urlparse(address).hostname in ("localhost", "::1", "127.0.0.1"):
			try:
				username, password = get_service_credentials_from_backend()
			except Exception as err:  # pylint: disable=broad-except
				logger.warning(err)

		jsonrpc_client = ServiceClient(
			address=address,
			username=username,
			password=password,
			user_agent=f"opsi-cli/{__version__}",
			session_lifetime=SESSION_LIFETIME,
			verify=ServiceVerificationModes.ACCEPT_ALL,
		)
	return jsonrpc_client
