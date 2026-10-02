"""Closed, bounded v1 wire contracts shared by control plane and worker."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

VERSION: Literal[1] = 1
MAX_MESSAGE = 1_500_000
MAX_INFLIGHT = 4
MAX_TRANSFER = 32 * 1024 * 1024
CHUNK_SIZE = 48 * 1024
KEYS = Literal[
    "enter",
    "tab",
    "escape",
    "backspace",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "space",
    "ctrl",
    "alt",
    "shift",
    "a",
    "c",
    "v",
    "x",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Strict):
    pass


class Page(Strict):
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=100, ge=1, le=200)
    filter: str = Field(default="", max_length=100)


class ProcessPage(Page):
    offset: int = Field(default=0, ge=0, le=2_147_483_647)


class PathInput(Strict):
    path: str = Field(min_length=1, max_length=2048)


class FileList(PathInput, Page):
    pass


class FileRead(PathInput):
    offset: int = Field(default=0, ge=0, le=MAX_TRANSFER)
    length: int = Field(default=CHUNK_SIZE, ge=1, le=CHUNK_SIZE)


class FileWrite(PathInput):
    content: str = Field(max_length=CHUNK_SIZE)
    overwrite: bool = False


class FileMove(PathInput):
    destination: str = Field(min_length=1, max_length=2048)
    overwrite: bool = False


class Start(Strict):
    alias: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    args: list[str] = Field(default_factory=list, max_length=16)


class Terminate(Strict):
    pid: int = Field(gt=0)
    expected_created_at: float = Field(gt=0)
    expected_name: str = Field(min_length=1, max_length=256)


class Text(Strict):
    text: str = Field(max_length=4096)


class Capture(Strict):
    monitor: int = Field(default=1, ge=1, le=16)


class Point(Capture):
    x: int = Field(ge=0, le=65535)
    y: int = Field(ge=0, le=65535)


class Click(Point):
    button: Literal["left", "middle", "right"] = "left"


class Key(Strict):
    key: KEYS


class Scroll(Strict):
    dx: int = Field(default=0, ge=-10, le=10)
    dy: int = Field(ge=-10, le=10)


class Navigate(Strict):
    url: str = Field(min_length=1, max_length=2048)


class Selector(Strict):
    selector: str = Field(min_length=1, max_length=512)


class BrowserText(Selector, Text):
    pass


class TransferBegin(PathInput):
    transfer_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    overwrite: bool = False


class TransferID(Strict):
    transfer_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class TransferChunk(TransferID):
    content_b64: str = Field(max_length=CHUNK_SIZE * 2)
    offset: int = Field(ge=0, le=MAX_TRANSFER)


# The closed operation catalog is authority, never supplied by a peer.
OPERATIONS: dict[str, tuple[type[Strict], Literal["read", "mutation"]]] = {
    "system.inspect": (Empty, "read"),
    "process.list": (ProcessPage, "read"),
    "file.list": (FileList, "read"),
    "file.read": (FileRead, "read"),
    "clipboard.read": (Empty, "read"),
    "screen.capture": (Capture, "read"),
    "browser.snapshot": (Empty, "read"),
    "file.write": (FileWrite, "mutation"),
    "file.mkdir": (PathInput, "mutation"),
    "file.delete": (PathInput, "mutation"),
    "file.move": (FileMove, "mutation"),
    "process.start": (Start, "mutation"),
    "process.terminate": (Terminate, "mutation"),
    "clipboard.write": (Text, "mutation"),
    "desktop.click": (Click, "mutation"),
    "desktop.move": (Point, "mutation"),
    "desktop.type": (Text, "mutation"),
    "desktop.key": (Key, "mutation"),
    "desktop.scroll": (Scroll, "mutation"),
    "browser.open": (Navigate, "mutation"),
    "browser.navigate": (Navigate, "mutation"),
    "browser.click": (Selector, "mutation"),
    "browser.type": (BrowserText, "mutation"),
    "browser.key": (Key, "mutation"),
    "browser.close": (Empty, "mutation"),
}
TRANSFERS: dict[str, tuple[type[Strict], Literal["read", "mutation"]]] = {
    "transfer.begin": (TransferBegin, "mutation"),
    "transfer.chunk": (TransferChunk, "mutation"),
    "transfer.finish": (TransferID, "mutation"),
    "transfer.abort": (TransferID, "mutation"),
}


class Geometry(Strict):
    left: int = Field(ge=-65535, le=65535)
    top: int = Field(ge=-65535, le=65535)
    width: int = Field(gt=0, le=65535)
    height: int = Field(gt=0, le=65535)


class Hello(Strict):
    type: Literal["hello"] = "hello"
    version: Literal[1] = VERSION
    platform: Literal["windows", "linux"]
    worker_version: str = Field(min_length=1, max_length=32)
    capabilities: list[str] = Field(max_length=32)
    geometry: list[Geometry] = Field(default_factory=list, max_length=16)


class Welcome(Strict):
    type: Literal["welcome"] = "welcome"
    version: Literal[1] = VERSION


class Request(Strict):
    type: Literal["request"] = "request"
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class Result(Strict):
    type: Literal["result"] = "result"
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    data: dict[str, Any] = Field(default_factory=dict)
    error: (
        Literal[
            "invalid_input",
            "policy_denied",
            "unavailable",
            "conflict",
            "cancelled",
            "outcome_unknown",
        ]
        | None
    ) = None


class Cancel(Strict):
    type: Literal["cancel"] = "cancel"
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class Ping(Strict):
    type: Literal["ping", "pong"]


MESSAGE: TypeAdapter[Hello | Welcome | Request | Result | Cancel | Ping] = TypeAdapter(
    Annotated[Hello | Welcome | Request | Result | Cancel | Ping, Field(discriminator="type")]
)


def decode(raw: str | bytes) -> Hello | Welcome | Request | Result | Cancel | Ping:
    if len(raw.encode() if isinstance(raw, str) else raw) > MAX_MESSAGE:
        raise ValueError("message_size")
    value = json.loads(raw)
    bound_json(value)
    return MESSAGE.validate_python(value)


def bound_json(value: Any, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("message_depth")
    if isinstance(value, (list, dict)):
        if len(value) > 512:
            raise ValueError("message_count")
        for child in value.values() if isinstance(value, dict) else value:
            bound_json(child, depth + 1)
    elif isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise ValueError("nonfinite")


def validate_url(url: str) -> str:
    """TLS except exact loopback; no embedded credentials/query/fragment."""
    import ipaddress

    parsed = urlsplit(url)
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = parsed.hostname == "localhost"
    if (
        parsed.scheme not in {"https", "http"}
        or (parsed.scheme == "http" and not local)
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("server_url_requires_tls")
    _ = parsed.port
    return url.rstrip("/")


class ScreenFrame(Strict):
    image_b64: str = Field(max_length=1_200_000, pattern=r"^[A-Za-z0-9+/]*={0,2}$")
    media_type: Literal["image/jpeg"]
    width: int = Field(gt=0, le=1920)
    height: int = Field(gt=0, le=1920)
    geometry: Geometry
    monitors: list[Geometry] = Field(max_length=16)
    max_fps: int = Field(ge=1, le=5)
