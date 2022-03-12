# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

opsi service
"""

from opsicommon.client.jsonrpc import JSONRPCClient  # type: ignore[import]

from opsicli.config import config

jsonrpc_client = None  # pylint: disable=invalid-name


def get_service_connection() -> JSONRPCClient:
	global jsonrpc_client  # pylint: disable=invalid-name,global-statement
	if not jsonrpc_client:
		jsonrpc_client = JSONRPCClient(address=config.service_url, username=config.username, password=config.password)
	return jsonrpc_client
