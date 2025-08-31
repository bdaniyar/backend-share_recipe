import logging
import logging.config
from logging.handlers import RotatingFileHandler
import os
import time
import uuid
import contextvars
from pathlib import Path
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable for per-request correlation
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get("-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Attach request_id to every record
        record.request_id = get_request_id()
        return True


def setup_logging(level: Optional[str] = None) -> None:
    """
    Configure logging:
    - Console + rotating file handler
    - Request ID filter added to all handlers
    - Integrates uvicorn loggers
    """
    # Resolve logs directory: <repo>/share-recipe-frontend/backend/logs
    base_dir = Path(__file__).resolve().parents[2]
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_file = os.getenv("LOG_FILE", str(logs_dir / "app.log"))

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIdFilter},
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s",
            },
            "uvicorn_access": {
                "format": '%(asctime)s %(levelname)s [uvicorn.access] [%(request_id)s] %(message)s',
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
                "filters": ["request_id"],
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "default",
                "filters": ["request_id"],
                "filename": log_file,
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": log_level, "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": log_level, "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": log_level, "propagate": False},
            # App-specific loggers can be added here; root covers most cases
        },
        "root": {"handlers": ["console", "file"], "level": log_level},
    }

    logging.config.dictConfig(config)
    logging.getLogger(__name__).info("Logging configured", extra={})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    - Assigns request_id for each request
    - Adds X-Request-ID response header
    - Logs request start and completion with latency
    """

    def _new_request_id(self) -> str:
        return uuid.uuid4().hex

    async def dispatch(self, request: Request, call_next) -> Response:
        token = _request_id_var.set(self._new_request_id())
        logger = logging.getLogger("app.request")
        start = time.monotonic()
        try:
            logger.info(
                "Incoming request %s %s from %s",
                request.method,
                request.url.path,
                request.client.host if request.client else "-",
            )
            response = await call_next(request)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Attach request id to response
            response.headers["X-Request-ID"] = get_request_id()
            logger.info(
                "Completed %s %s -> %s in %dms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        except Exception:
            logger.exception("Unhandled error in request %s %s", request.method, request.url.path)
            raise
        finally:
            _request_id_var.reset(token)
