"""ASGI middleware that runs before the body is read.

`_read_capped` in `api/documents.py` bounds how much of an upload reaches
*memory*, and its docstring is accurate about that. It is not, however, a
bound on what reaches *disk*: by the time a handler's `UploadFile`
parameter is resolvable, Starlette and `python-multipart` have already
consumed the whole request body and spooled it to a
`SpooledTemporaryFile`, which rolls over to a real temp file past a small
threshold. A single multi-gigabyte POST therefore fills the disk before
the handler is entered and before any cap is consulted.

The cap has to be applied at the ASGI layer, where the bytes actually
arrive, so this runs outside the router.
"""
from __future__ import annotations

import logging

from starlette.datastructures import Headers

logger = logging.getLogger(__name__)

# Multipart framing (boundaries, per-part headers, trailing CRLFs) makes
# the encoded body somewhat larger than the file inside it. Allowing a
# megabyte of overhead keeps a file that is legitimately just under the
# limit from being rejected for its envelope, while still bounding the
# request to something of the same order as the limit itself.
_FRAMING_SLACK_BYTES = 1024 * 1024

_RESPONSE = (
    b'{"detail":"request body exceeds the maximum allowed size"}'
)


class _BodyTooLarge(Exception):
    """Raised from inside `receive` once the cap is passed."""


class MaxBodySizeMiddleware:
    """Refuses an over-sized request body before anything spools it.

    Two checks, because either alone has a hole:

    * A declared `Content-Length` over the limit is rejected immediately,
      without reading a single byte.
    * A body that arrives chunked carries no `Content-Length`, so bytes
      are counted as they stream and the request is abandoned the moment
      the running total passes the limit. Without this, declaring no
      length would bypass the check entirely.
    """

    def __init__(self, app, *, max_bytes: int, slack_bytes: int = _FRAMING_SLACK_BYTES) -> None:
        self.app = app
        self.limit = max_bytes + slack_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.limit:
                    await self._reject(send)
                    return
            except ValueError:
                # A malformed Content-Length is not ours to adjudicate --
                # fall through to the streaming count, which does not
                # trust the header anyway.
                pass

        received = 0
        started = False

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            # If the application already began responding we cannot
            # replace the status; the connection simply ends short, which
            # is the correct outcome for a client that overran the limit.
            if not started:
                await self._reject(send)

    async def _reject(self, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_RESPONSE)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _RESPONSE})
