# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

utils
"""

from __future__ import annotations

import base64
import os
import platform
import random
import shutil
import stat
import string
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Type

from opsicommon.logging import (
	get_logger,  # type: ignore[import]
	use_logging_config,
)
from opsicommon.system.info import is_posix, is_windows

if is_windows():
	import win32console  # type: ignore[import-not-found]
else:
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
	if not is_windows():
		raise NotImplementedError(
			f"add_to_env_variable is currently only implemented for windows - If necessary, manually add {value} to {key}"
		)

	if key.upper() != "PATH":
		raise NotImplementedError("Only PATH is currently supported")

	import winreg

	import win32process  # type: ignore[import] # pylint: disable=import-outside-toplevel,import-error

	key_handle = winreg.CreateKey(  # type: ignore[attr-defined]
		winreg.HKEY_LOCAL_MACHINE if system else winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
		r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment" if system else r"Environment",
	)
	try:
		if win32process.IsWow64Process():
			winreg.DisableReflectionKey(key_handle)  # type: ignore[attr-defined]

		try:
			reg_value, value_type = winreg.QueryValueEx(key_handle, key)  # type: ignore[attr-defined]
			cur_reg_values = reg_value.split(";")
			# Do some cleanup also.
			# Remove empty values and values containing "pywin32_system32" and "opsi"
			reg_values = list(dict.fromkeys(v for v in cur_reg_values if v and not ("pywin32_system32" in v and "opsi" in v)))
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
def raw_terminal() -> Iterator[None]:
	with use_logging_config(stderr_level=0):
		if is_windows():
			con_buf_in = win32console.GetStdHandle(-10)  # STD_INPUT_HANDLE /  CONIN$
			mode_in = con_buf_in.GetConsoleMode()
			con_buf_out = win32console.GetStdHandle(-11)  # STD_OUTPUT_HANDLE /  CONOUT$
			mode_out = con_buf_out.GetConsoleMode()
			# Disable line input, echo input
			# con_buf_in.SetConsoleMode(mode_in & ~0x2  & ~0x4)
			con_buf_in.SetConsoleMode(mode_in & ~0x1 & ~0x2 & ~0x4)
			try:
				yield
			finally:
				con_buf_in.SetConsoleMode(mode_in)
				con_buf_out.SetConsoleMode(mode_out)
		else:
			attrs = termios.tcgetattr(sys.stdin.fileno())
			try:
				tty.setraw(sys.stdin.fileno())  # Set raw mode to access char by char
				yield
			except Exception as err:
				logger.error(err, exc_info=True)
				termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)
				print(err, file=sys.stderr)
			else:
				termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)


@lru_cache
def user_is_admin() -> bool:
	try:
		return os.geteuid() == 0
	except AttributeError:
		import ctypes

		return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]


def evaluate_rpc_dict_result(result: dict[str, dict[str, str | None]], log_success: bool = True) -> int:
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
	import requests

	new_file = destination / url.split("/")[-1]
	response = requests.get(url, stream=True, timeout=30)
	response.raise_for_status()
	with open(new_file, "wb") as filehandle:
		shutil.copyfileobj(response.raw, filehandle)

	if make_executable:
		os.chmod(new_file, os.stat(new_file).st_mode | stat.S_IEXEC)
	return new_file


def get_opsi_cli_download_filename() -> str:
	system = platform.system().lower()
	machine = platform.machine().lower()
	if system == "windows":
		return "opsi-cli-windows-x86.exe"
	if system == "linux":
		if machine == "aarch64":
			return "opsi-cli-linux-arm64.run"
		return "opsi-cli-linux-x64.run"
	if system == "darwin":
		if machine == "aarch64":
			return "opsi-cli-macos-arm64"
		return "opsi-cli-macos-x64"
	raise ValueError(f"Invalid platform {system}")


def install_binary(source: Path | str, destination: Path | str) -> None:
	if not isinstance(source, Path):
		source = Path(source)
	if not isinstance(destination, Path):
		destination = Path(destination)
	source = source.resolve()
	destination = destination.resolve()
	if source == destination:
		return

	if not destination.parent.exists():
		destination.parent.mkdir(parents=True)

	backup_path = None
	if destination.exists() and destination.is_file():
		backup_path = destination.with_suffix(destination.suffix + ".old")
		if backup_path.exists():
			backup_path.unlink()
		shutil.move(destination, backup_path)
	try:
		shutil.copy(source, destination)
	except Exception as err:
		logger.error("Failed to install binary from '%s' to '%s': %s", source, destination, err)
		if backup_path:
			logger.warning("Restoring backup.")
			shutil.move(backup_path, destination)
		raise
	else:
		if backup_path:
			backup_path.unlink()
		if is_posix():
			os.chmod(destination, 0o755)


def retry(
	retries: int = 3, wait: float = 0, exceptions: Iterable[Type[Exception]] | None = None, caught_exceptions: list[Exception] | None = None
) -> Callable:
	"""
	Decorator to retry a function.
	:param retries: Number of retries
	:param wait: Time to wait between retries
	:param exceptions: Exception to catch, if None catch all exceptions
	"""
	attempts = 1 + retries

	def decorator(func: Callable) -> Callable:
		def wrapper(*args: Any, **kwargs: Any) -> Any:
			for attempt in range(1, attempts + 1):
				try:
					return func(*args, **kwargs)
				except Exception as exc:
					logger.warning("Attempt %d of %d failed with [%s] %s", attempt, attempts, exc.__class__.__name__, exc)
					if attempt == attempts:
						logger.debug("No retry because the maximum number of %d attempts has been reached", attempts)
						raise
					if exceptions and not any(isinstance(exc, exc_type) for exc_type in exceptions):
						logger.debug("No retry because excetion type %s is not in %s", exc.__class__.__name__, exceptions)
						raise
					if caught_exceptions is not None:
						caught_exceptions.append(exc)
					if wait > 0:
						time.sleep(wait)

		return wrapper

	return decorator


def create_nested_dict(items: list[object], attributes: list[str]) -> dict:
	"""
	Parameters:
	items: List of objects to be converted into a dictionary.
	attributes: List of attribute names to be used as keys in the dictionary.

	Returns:
	A nested dictionary where each level corresponds to an attribute in keys.
	"""
	info_dict: dict[Any, Any] = defaultdict(dict)
	for item in items:
		temp_dict = info_dict
		for key in attributes[:-1]:
			key_value = getattr(item, key, None)
			temp_dict = temp_dict.setdefault(key_value, defaultdict(dict))
		temp_dict[getattr(item, attributes[-1] if attributes else "", "")] = item
	return info_dict
