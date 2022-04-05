# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

opsi service
"""

from opsicommon.client.jsonrpc import JSONRPCClient  # type: ignore[import]
from opsicommon.logging import logger, secret_filter  # type: ignore[import]

from opsicli import __version__
from opsicli.cache import cache
from opsicli.config import config

jsonrpc_client = None  # pylint: disable=invalid-name


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
