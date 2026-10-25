"""Optional HTTP Basic auth, enabled by setting PYTORRENT_PASSWORD."""

import base64
import binascii
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse


class PasswordMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, password: str) -> None:
        super().__init__(app)
        self._password = password.encode()

    async def dispatch(self, request: Request, call_next):
        if self._authorized(request.headers.get("authorization", "")):
            return await call_next(request)
        return PlainTextResponse(
            "Password required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="PyTorrent", charset="UTF-8"'},
        )

    def _authorized(self, header: str) -> bool:
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return False
        # Any username is accepted; only the password is checked
        _, _, password = decoded.partition(b":")
        return secrets.compare_digest(password, self._password)
