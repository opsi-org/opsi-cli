"""
opsi-cli tests (general test setup)
"""

import os

OPSI_HOSTNAME = os.environ.get("OPSI_HOST", "localhost")
OPSI_USERNAME = os.environ.get("OPSI_USERNAME", "adminuser")
OPSI_PASSWORD = os.environ.get("OPSI_PASSWORD", "vhahd8usaz")
