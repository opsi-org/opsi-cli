"""
websocket functions
"""

import asyncio
import ssl
from base64 import b64encode
from typing import Optional

import msgspec
import websockets
from opsicommon.logging import logger
from prompt_toolkit.shortcuts.prompt import PromptSession

from opsicli.io import get_console, prompt

WS_TERMINAL_PATH = "/admin/terminal/ws"
# WS_TERMINAL_PATH = "/ws/terminal"


def basic_auth(username, password):
	token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
	return f"Basic {token}"


class Messagebus:
	def __init__(self, url: str, username: str, password: Optional[str] = None) -> None:
		self.url = url.replace("https://", "wss://")
		self.username = username
		self.password = password or prompt(f"password for user {username}", password=True)

	async def terminal_receiver(self, websocket):
		logger.info("Starting terminal receiver.")
		console = get_console()
		while True:
			try:
				data = msgspec.msgpack.decode(await websocket.recv())
				if data.get("type") == "terminal-read":
					console.print(data.get("payload").decode("utf-8"), end="")
				else:
					logger.warning("Strange message received: type %r, payload %r", data.get("type"), data.get("payload"))
			except websockets.exceptions.ConnectionClosed as closed:
				if isinstance(closed, websockets.exceptions.ConnectionClosedOK):
					logger.notice("Websocket connection closed: %s", closed, exc_info=False)
				else:
					logger.error("Websocket connection closed: %s", closed, exc_info=True)
				break

	async def terminal_sender(self, websocket):
		logger.info("Starting terminal sender.")
		prompt_session = PromptSession()
		while True:
			try:
				input_string = await prompt_session.prompt_async("")
				data = {"payload": input_string + "\n", "type": "terminal-write"}
				await websocket.send(msgspec.msgpack.encode(data))
			except websockets.exceptions.ConnectionClosed as closed:
				if isinstance(closed, websockets.exceptions.ConnectionClosedOK):
					logger.notice("Websocket connection closed: %s", closed, exc_info=False)
				else:
					logger.error("Websocket connection closed: %s", closed, exc_info=True)
				break
			except EOFError:
				break

	async def run_terminal(self):
		ctx = ssl.create_default_context()
		ctx.check_hostname = False
		ctx.verify_mode = ssl.CERT_NONE
		username = "adminuser"
		password = "linux123"  # str(prompt("Password"))
		extra_headers = {"Authorization": basic_auth(username, password)}
		async with websockets.connect(  # pylint: disable=no-member # damn lazy imports again
			f"{self.url}{WS_TERMINAL_PATH}", ssl=ctx, extra_headers=extra_headers
		) as websocket:
			logger.notice("Connecting to terminal websocket.")
			receiver_task = asyncio.ensure_future(self.terminal_receiver(websocket))
			sender_task = asyncio.ensure_future(self.terminal_sender(websocket))
			await asyncio.wait(
				[receiver_task, sender_task],
				return_when=asyncio.FIRST_COMPLETED,
			)
