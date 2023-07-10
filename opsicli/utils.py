# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

utils
"""

import base64
import os
import platform
import random
import string
import subprocess
import sys
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from opsicommon.logging import get_logger, logging_config  # type: ignore[import]

if platform.system().lower() != "windows":
	import termios
	import tty


logger = get_logger("opsicli")


def random_string(length: int) -> str:
	letters = string.ascii_letters + string.digits
	return "".join(random.choice(letters) for _ in range(length))


def encrypt(cleartext: str) -> str:
	if not cleartext:
		raise ValueError("Invalid cleartext")
	key = random_string(16)
	cipher = ""
	for num, char in enumerate(cleartext):
		key_c = key[num % len(key)]
		cipher += chr((ord(char) + ord(key_c)) % 256)
	return "{crypt}" + base64.urlsafe_b64encode(f"{key}:{cipher}".encode("utf-8")).decode("ascii")


def decrypt(cipher: str) -> str:
	if not cipher:
		raise ValueError("Invalid cipher")
	if not cipher.startswith("{crypt}"):
		return cipher
	cipher = cipher.replace("{crypt}", "")
	cleartext = ""
	cipher = base64.urlsafe_b64decode(cipher).decode("utf-8")
	key, cipher = cipher.split(":", 1)
	for num, char in enumerate(cipher):
		key_c = key[num % len(key)]
		cleartext += chr((ord(char) - ord(key_c) + 256) % 256)
	return cleartext


def add_to_env_variable(key: str, value: str, system: bool = False) -> None:
	if platform.system().lower() != "windows":
		raise NotImplementedError(
			f"add_to_env_variable is currently only implemented for windows - If necessary, manually add {value} to {key}"
		)
	if value in os.environ.get(key, ""):
		logger.info("%s already in Environment Variable %s", value, key)
		return
	call = f'setx {key} "%{key}%;{value}" /M' if system else f'setx {key} "%{key}%;{value}"'
	logger.notice("Adding %s to Environment Variable %s", value, key)
	subprocess.check_output(call, shell=True)


@contextmanager
def stream_wrap() -> Iterator[None]:
	logging_config(stderr_level=0)  # Restore?
	if platform.system().lower() == "windows":
		yield
	else:
		attrs = termios.tcgetattr(sys.stdin.fileno())
		try:
			tty.setraw(sys.stdin.fileno())  # Set raw mode to access char by char
			yield
		except Exception as err:  # pylint: disable=broad-except
			termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)
			print(err, file=sys.stderr)
		else:
			termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)


@lru_cache
def user_is_admin() -> bool:
	try:
		return os.geteuid() == 0
	except AttributeError:
		import ctypes  # pylint: disable=import-outside-toplevel

		return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
