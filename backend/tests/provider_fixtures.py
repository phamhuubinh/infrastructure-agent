"""Shared raw HTTP/SSE fixture transport; no live account or native-app proof."""

import httpx


class SplitStream(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body.encode()
        self.closed = False

    async def __aiter__(self):
        for offset in range(0, len(self.body), 3):
            yield self.body[offset : offset + 3]

    async def aclose(self):
        self.closed = True


def use_provider(monkeypatch, provider):
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(provider), **kwargs),
    )
