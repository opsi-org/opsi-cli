"""
opsi-cli Basic command line interface for opsi
"""

import os
import tempfile
import platform

if platform.system().lower() == "windows":
	# TODO: use a temporary directory to store plugins (Permission issue)
	CLI_BASE_PATH = os.path.join(tempfile.gettempdir(), "opsicli")
else:
	CLI_BASE_PATH = os.path.join(os.path.expanduser("~"), ".local", "lib", "opsicli")
COMMANDS_DIR = os.path.join(CLI_BASE_PATH, "commands")
LIB_DIR = os.path.join(CLI_BASE_PATH, "lib")
