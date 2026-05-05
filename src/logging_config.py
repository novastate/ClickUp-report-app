"""Shared logging configuration for the Sprint Reporter app.

Call configure_logging() once at app startup. It's idempotent — second
call is a no-op so importing modules can safely call it defensively.
"""
import logging
import logging.handlers

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_path: str = "app.log", level: str = "INFO") -> None:
    """Set up root logger with rotating file + stdout handlers.

    File rotates at 5MB, keeps 5 backups (so app.log + app.log.1..app.log.5).
    Tames chatty libraries (httpx, apscheduler) to WARNING level.
    Idempotent: subsequent calls return immediately.
    """
    if getattr(configure_logging, "_done", False):
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    configure_logging._done = True
