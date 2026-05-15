from __future__ import annotations

import logging


LOGGER = logging.getLogger("uvicorn.error")


def debug_log(message: str) -> None:
    """Writes debug messages to stdout and the uvicorn logger."""
    print(message, flush=True)
    LOGGER.info(message)
