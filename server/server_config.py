# server_config.py

"""
This module contains configuration settings for the P2P server.
"""
import logging


# Logging configuration
class CustomFormatter(logging.Formatter):
    RED = "\033[91m"
    GREEN = "\033[92m"
    PURPLE = "\033[95m"
    RESET = "\033[0m"
    BLACK_BG = "\033[40m"
    WHITE_BG = "\033[47m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    def format(self, record):
        levelname_color = CustomFormatter.WHITE  # Default color

        if record.levelno == logging.DEBUG:
            levelname_color = CustomFormatter.CYAN
        elif record.levelno == logging.INFO:
            levelname_color = CustomFormatter.GREEN
        elif record.levelno == logging.WARNING:
            levelname_color = CustomFormatter.YELLOW
        elif record.levelno == logging.ERROR:
            levelname_color = CustomFormatter.RED

        levelname_color = f"{CustomFormatter.BLACK_BG}{levelname_color}"

        if record.levelno == logging.ERROR:
            record.msg = f"{CustomFormatter.RED}{record.msg}{CustomFormatter.RESET}"
        record.filename = (
            f"{CustomFormatter.PURPLE}{record.filename}{CustomFormatter.RESET}"
        )
        formatter_string = f"{CustomFormatter.BLACK_BG}{CustomFormatter.GREEN}%(asctime)s - %(filename)s - {levelname_color}%(levelname)s{CustomFormatter.RESET} - %(message)s"
        return logging.Formatter(formatter_string, datefmt="%Y-%m-%d %H:%M:%S").format(
            record
        )


class NoColorFormatter(logging.Formatter):
    def format(self, record):
        formatter_string = "%(asctime)s - %(filename)s - %(levelname)s - %(message)s"
        return logging.Formatter(formatter_string, datefmt="%Y-%m-%d %H:%M:%S").format(
            record
        )


formatter = CustomFormatter(
    fmt="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

no_color_formatter = NoColorFormatter(
    fmt="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

file_handler = logging.FileHandler('server.log')
file_handler.setFormatter(no_color_formatter)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(stream_handler)
LOGGER.addHandler(file_handler)

# Default port for P2P server
DEFAULT_P2P_PORT = 9828

# WebSocket server port
WEBSOCKET_PORT = 9000

# HTTP server port
HTTP_API_PORT = 8081

# Bootstrap addresses for P2P network
BOOTSTRAP_ADDRESSES = [
    "192.168.86.109:9828",
    "192.168.86.30:9828",
    "34.35.78.201:9828",
]

# Database file for storing spammer data
DATABASE_FILE = "spammers.db"

BEACON = False
# Set to True to enable beacon mode
# Set to False to disable beacon mode

DISABLE_DB = False
# Set to True to disable database functionality
# Set to False to enable database functionality
