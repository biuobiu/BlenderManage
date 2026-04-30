import logging
import os
import sys
from logging.handlers import RotatingFileHandler


LOG_FILE_NAME = "blender_manager.log"


class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._logger = logging.getLogger("BlenderManager")
        self._logger.setLevel(logging.DEBUG)
        self._setup_handlers()

    def _setup_handlers(self):
        log_dir = os.path.join(os.path.expanduser("~"), ".BlenderManager", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, LOG_FILE_NAME)

        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        self._logger.addHandler(file_handler)

        stream = sys.stdout or sys.__stdout__ or sys.__stderr__
        if stream:
            console_handler = logging.StreamHandler(stream)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                "%(levelname)s: %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            self._logger.addHandler(console_handler)

    @property
    def logger(self):
        return self._logger

    def debug(self, message, *args, **kwargs):
        self._logger.debug(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._logger.error(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self._logger.critical(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self._logger.exception(message, *args, **kwargs)
