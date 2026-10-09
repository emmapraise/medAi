import logging
import sys

from app.config import settings


def configure_logging() -> None:
    """Configure root logging once; level is DEBUG outside production."""
    logging.basicConfig(
        level=logging.INFO if settings.IS_PRODUCTION else logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
