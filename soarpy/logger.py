"""Shared logging setup for soarpy."""

import logging

from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging with a Rich-formatted handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_download(index: int, total: int, filename: str, dest: str) -> None:
    logger = get_logger(__name__)
    logger.info(f"[{index}/{total}] Downloading {filename} -> {dest}")
