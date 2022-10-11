# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

utils
"""

import base64
import platform
import random
import string
import subprocess


def random_string(length):
	letters = string.ascii_letters + string.digits
	return "".join(random.choice(letters) for _ in range(length))


def encrypt(cleartext: str):
	if not cleartext:
		raise ValueError("Invalid cleartext")
	key = random_string(16)
	cipher = ""
	for num, char in enumerate(cleartext):
		key_c = key[num % len(key)]
		cipher += chr((ord(char) + ord(key_c)) % 256)
	return "{crypt}" + base64.urlsafe_b64encode(f"{key}:{cipher}".encode("utf-8")).decode("ascii")


def decrypt(cipher: str):
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
	call = f'setx {key} "%{key}%;{value}" /M' if system else f'setx {key} "%{key}%;{value}"'
	subprocess.check_call(call, shell=True)
