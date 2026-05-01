"""
CORS middleware for widget endpoints only.

Validates Origin header against client's widget_allowed_origins whitelist.
Non-widget paths are passed through unchanged.
"""
import os
import logging
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
        if origin not in allowed_origins:
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
    if origin not in allowed_origins:
        return Response(status_code=403, content="Origin not allowed")

    # Process request
    response = await call_next(request)

    # Attach CORS headers to response
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"

    return response
