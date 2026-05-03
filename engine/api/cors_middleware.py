"""
CORS middleware for widget endpoints only.

Validates Origin header against client's widget_allowed_origins whitelist.
Non-widget paths are passed through unchanged.
"""
import os
import logging
from urllib.parse import urlsplit
from fastapi import Request, Response
from engine.config.client_config import load_client_config, ClientNotFoundError

logger = logging.getLogger(__name__)

LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:5500",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5500",
]

WIDGET_PATH_PREFIXES = ("/chat/", "/widget/")


def _normalize_origin(value: str) -> str:
    """Return canonical scheme://host[:port] origin string or empty on invalid input."""
    if not value:
        return ""

    raw = value.strip().rstrip("/")
    if not raw:
        return ""

    # Origin header is scheme://host[:port]. Allow host-only entries in config.
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname
    if not host:
        return ""

    if parsed.scheme:
        origin = f"{parsed.scheme.lower()}://{host.lower()}"
        if parsed.port:
            origin = f"{origin}:{parsed.port}"
        return origin

    # Host-only allowlist entry
    host_only = host.lower()
    if parsed.port:
        host_only = f"{host_only}:{parsed.port}"
    return host_only


def _is_origin_allowed(origin: str, allowed_origins: list[str]) -> bool:
    """Validate request origin against normalized exact, host-only, and wildcard entries."""
    normalized_request = _normalize_origin(origin)
    if not normalized_request or "://" not in normalized_request:
        return False

    request_host_port = normalized_request.split("://", 1)[1]

    exact_matches: set[str] = set()
    host_matches: set[str] = set()
    wildcard_matches: list[str] = []

    for allowed in allowed_origins:
        item = _normalize_origin(allowed)
        if not item:
            continue

        if item.startswith("*."):
            wildcard_matches.append(item[2:])
            continue

        if "://" in item:
            exact_matches.add(item)
        else:
            host_matches.add(item)

    if normalized_request in exact_matches:
        return True

    if request_host_port in host_matches:
        return True

    request_host = request_host_port.split(":", 1)[0]
    for wildcard in wildcard_matches:
        # wildcard supports hosts like *.example.com (not apex example.com)
        wildcard_host = wildcard.split(":", 1)[0]
        if request_host.endswith(f".{wildcard_host}"):
            return True

    return False


async def widget_cors_middleware(request: Request, call_next):
    """
    CORS middleware for widget endpoints only.
    Validates Origin header against client's widget_allowed_origins whitelist.
    Non-widget paths are passed through unchanged.
    """
    path = request.url.path

    # Pass through non-widget endpoints untouched
    if not any(path.startswith(prefix) for prefix in WIDGET_PATH_PREFIXES):
        return await call_next(request)

    # No Origin header — allow immediately (curl, Postman, same-origin, TestClient)
    # No need to load ClientConfig when there's nothing to validate.
    origin = request.headers.get("Origin")
    if not origin:
        return await call_next(request)

    # Extract client_id from path
    # /chat/{client_id}/... or /widget/{client_id}.js
    parts = path.lstrip("/").split("/")
    if len(parts) < 2:
        return Response(status_code=400, content="Invalid path")
    client_id = parts[1]
    if path.startswith("/widget/"):
        # path is /widget/flow-ai.js → parts[1] is "flow-ai.js" → strip ".js"
        client_id = client_id.removesuffix(".js")

    # Load ClientConfig (cached) — only when Origin header is present
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        return Response(status_code=404, content="Client not found")
    except Exception as e:
        logger.error(f"CORS middleware: failed to load client config for {client_id}: {e}")
        return Response(status_code=500, content="Internal server error")

    # Build allowed origins list
    allowed_origins: list[str] = [
        o.strip()
        for o in (client_config.widget_allowed_origins or "").split(",")
        if o.strip()
    ]
    if os.getenv("ENVIRONMENT", "production") == "development":
        allowed_origins.extend(LOCALHOST_ORIGINS)

    # OPTIONS preflight — validate and return early
    if request.method == "OPTIONS":
        if not _is_origin_allowed(origin, allowed_origins):
            return Response(status_code=403, content="Origin not allowed")
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "86400",
            },
        )

    # Non-OPTIONS: validate origin
    if not _is_origin_allowed(origin, allowed_origins):
        return Response(status_code=403, content="Origin not allowed")

    # Process request
    response = await call_next(request)

    # Attach CORS headers to response
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"

    return response
