"""Unified logging via loguru."""
import sys

from loguru import logger

from src.utils.config import settings


def setup_logging() -> None:
    """Configure loguru with project settings."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        enqueue=False,
        backtrace=True,
        diagnose=False,
    )


__all__ = ["logger", "setup_logging"]