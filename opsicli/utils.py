# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

utils
"""

import base64
import os
import platform
import random
import shutil
import stat
import string
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
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
	return "{crypt}" + base64.urlsafe_b64encode(
		f"{key}:{cipher}".encode("utf-8")
	).decode("ascii")


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

	if key.upper() != "PATH":
		raise NotImplementedError("Only PATH is currently supported")

	import winreg  # pylint: disable=import-outside-toplevel,import-error

	import win32process  # type: ignore[import] # pylint: disable=import-outside-toplevel,import-error

	key_handle = winreg.CreateKey(  # type: ignore[attr-defined]
		winreg.HKEY_LOCAL_MACHINE if system else winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
		r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
		if system
		else r"Environment",
	)
	try:
		if win32process.IsWow64Process():
			winreg.DisableReflectionKey(key_handle)  # type: ignore[attr-defined]

		try:
			reg_value, value_type = winreg.QueryValueEx(key_handle, key)  # type: ignore[attr-defined]
			cur_reg_values = reg_value.split(";")
			# Do some cleanup also.
			# Remove empty values and values containing "pywin32_system32" and "opsi"
			reg_values = list(
				dict.fromkeys(
					v
					for v in cur_reg_values
					if v and not ("pywin32_system32" in v and "opsi" in v)
				)
			)
			if value.lower() in (v.lower() for v in reg_values):
				logger.info("%r already in environment variable %r", value, key)
			else:
				logger.notice("Adding %r to environment variable %r", value, key)
				reg_values.append(value)

			if reg_values == cur_reg_values:
				# Unchanged
				return

			reg_value = ";".join(reg_values)
			winreg.SetValueEx(key_handle, key, 0, value_type, reg_value)  # type: ignore[attr-defined]
		except FileNotFoundError as err:
			raise ValueError(f"Key {key!r} not found in registry") from err
	finally:
		winreg.CloseKey(key_handle)  # type: ignore[attr-defined]


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


def evaluate_rpc_dict_result(
	result: dict[str, dict[str, str | None]], log_success: bool = True
) -> int:
	num_success = 0
	for key, response in result.items():
		if response.get("error"):
			logger.warning("%s: ERROR %s", key, response["error"])
		else:
			if log_success:
				logger.info("%s: SUCCESS", key)
			num_success += 1
	return num_success


def download(url: str, destination: Path, make_executable: bool = False) -> Path:
	import requests  # pylint: disable=import-outside-toplevel

	new_file = destination / url.split("/")[-1]
	response = requests.get(url, stream=True, timeout=30)
	with open(new_file, "wb") as filehandle:
		shutil.copyfileobj(response.raw, filehandle)

	if make_executable:
		os.chmod(new_file, os.stat(new_file).st_mode | stat.S_IEXEC)
	return new_file


def get_opsi_cli_filename() -> str:
	system = platform.system().lower()
	if system == "windows":
		return "opsi-cli-windows.exe"
	if system == "linux":
		return "opsi-cli-linux.run"
	if system == "darwin":
		return "opsi-cli-macos"
	raise ValueError(f"Invalid platform {system}")


def replace_binary(current: Path, new: Path) -> None:
	backup_path = current.with_suffix(current.suffix + ".old")
	if backup_path.exists():
		backup_path.unlink()
	shutil.move(current, backup_path)
	try:
		shutil.move(new, current)
	except Exception as error:  # pylint: disable=broad-except
		logger.error("Failed to move binary to '%s'.", error)
		logger.warning("Restoring backup.")
		shutil.move(backup_path, current)
		raise
