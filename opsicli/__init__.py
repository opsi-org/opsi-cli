import os
import logging
import colorlog

CLI_BASE_PATH = os.path.expanduser("~/.local/lib/opsicli")
COMMANDS_DIR = os.path.join(CLI_BASE_PATH, "commands")
LIB_DIR = os.path.join(CLI_BASE_PATH, "lib")

logger = logging.getLogger()

LOG_COLORS = {
	'DEBUG': 'white',
	'INFO': 'green',
	'WARNING': 'bold_yellow',
	'ERROR': 'red',
	'CRITICAL': 'bold_red'
}

def init_logging(log_level):
	handler = colorlog.StreamHandler()
	handler.setFormatter(colorlog.ColoredFormatter(log_colors=LOG_COLORS))
	logger.addHandler(handler)
	logger.setLevel(getattr(logging, log_level.upper()))
