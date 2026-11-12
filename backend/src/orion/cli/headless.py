"""Terminal transport for the canonical Orion owner API."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import sys
import time
import unicodedata
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ValidationError

from orion.contracts import MutationMode
from orion.contracts.native_auth import NativeTokenPair
from orion.contracts.requests import RequestEventPage, RequestView
from orion.paths import ORION_HEALTH_IDENTITY, ORION_HOST, ORION_PORT

DEFAULT_ORIGIN = f"http://{ORION_HOST}:{ORION_PORT}"
ACTIVE = {"queued", "running"}
EXIT_STATUS = {"completed": 0, "failed": 1, "incomplete": 3, "cancelled": 130}
MAX_PROMPT_CHARS = 262_144
MAX_PROMPT_BYTES = MAX_PROMPT_CHARS * 4
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ClientError(Exception):
    """Only fixed diagnostics and numeric HTTP status are printed."""


def _origin(value: str) -> str:
    if any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in value):
        raise ClientError("Invalid Orion server origin.")
    try:
        parsed = urlsplit(value)
        canonical = str(httpx.URL(value)).removesuffix("/")
        port = parsed.port
    except (ValueError, httpx.InvalidURL):
        raise ClientError("Invalid Orion server origin.") from None
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or any(char in parsed.netloc for char in "@%\\")
        or parsed.path
        or "?" in value
        or "#" in value
        or port in {0, 443 if parsed.scheme == "https" else 80}
        or value != canonical
    ):
        raise ClientError("Use a canonical Orion server origin without a path or credentials.")
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ClientError("Remote Orion servers require HTTPS.")
    return value


def _segment(value: str) -> str:
    if not value or value in {".", ".."} or any(char in "/\\" or ord(char) < 32 for char in value):
        raise ClientError("Invalid Orion resource identifier.")
    return quote(value, safe="")


def _parse[T: BaseModel](model: type[T], value: Any) -> T:
    try:
        return model.model_validate(value)
    except ValidationError:
        raise ClientError("Orion returned an incompatible API response.") from None


class OwnerAPI:
    def __init__(self, http: httpx.Client, origin: str) -> None:
        self.http = http
        self.origin = origin
        self.access_token = os.environ.get("ORION_CLI_ACCESS_TOKEN")
        self.tokens: NativeTokenPair | None = None
        self.cookie_session = False
        if self.access_token and not (
            self.access_token.isascii()
            and all(char.isalnum() or char in "-_" for char in self.access_token)
            and 32 <= len(self.access_token) <= 128
        ):
            raise ClientError("Invalid ORION_CLI_ACCESS_TOKEN.")

    def identify(self) -> None:
        if self.request("GET", "/api/health", public=True) != {
            "identity": ORION_HEALTH_IDENTITY,
            "status": "ok",
        }:
            raise ClientError("The server did not identify itself as Orion.")

    def enroll(self) -> None:
        if self.access_token:
            raise ClientError("Select enrollment or ORION_CLI_ACCESS_TOKEN.")
        self.tokens = _parse(
            NativeTokenPair,
            self.request(
                "POST",
                "/api/auth/native/enroll",
                body={
                    "code": _secret("Orion enrollment code: "),
                    "name": "Orion CLI",
                    "platform": "linux",
                },
                public=True,
            ),
        )

    def login(self) -> None:
        if not self.origin.startswith("https://") or self.access_token:
            raise ClientError("Password login requires HTTPS and no ORION_CLI_ACCESS_TOKEN.")
        self.cookie_session = True
        self.request(
            "POST", "/api/auth/login", body={"password": _secret("Orion owner password: ")}
        )
        if not self.http.cookies:
            raise ClientError("Orion did not establish an owner session.")

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: Mapping[str, str | int] | None = None,
        retry: bool = False,
        public: bool = False,
    ) -> Any:
        if not public and self.tokens and self.tokens.access_expires_at <= time.time() + 5:
            self.tokens = _parse(
                NativeTokenPair,
                self.request(
                    "POST",
                    "/api/auth/native/refresh",
                    body={"refresh_token": self.tokens.refresh_token},
                    public=True,
                ),
            )
        token = (
            (self.tokens.access_token if self.tokens else self.access_token) if not public else None
        )
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if self.cookie_session:
            headers["Origin"] = self.origin
        for attempt in range(2 if retry else 1):
            if not self.cookie_session:
                self.http.cookies.clear()
            try:
                with self.http.stream(
                    method, self.origin + path, headers=headers, json=body, params=params
                ) as response:
                    if not response.is_success:
                        raise ClientError(f"Orion API returned HTTP {response.status_code}.")
                    if response.status_code == 204:
                        return None
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65_536):
                        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ClientError("Orion API response exceeded the client limit.")
                        data.extend(chunk)
                    return json.loads(data)
            except httpx.TransportError:
                if not retry or attempt:
                    raise ClientError("Orion API transport failed.") from None
            except (ValueError, RecursionError, httpx.DecodingError):
                raise ClientError("Orion API returned an invalid response.") from None
        raise AssertionError("Unreachable retry state")

    def close_session(self) -> None:
        if self.tokens or (self.cookie_session and self.http.cookies):
            try:
                path = "/api/auth/native/logout" if self.tokens else "/api/auth/logout"
                self.request("POST", path)
            except ClientError:
                print("Could not revoke this invocation's owner session.", file=sys.stderr)


def _secret(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (EOFError, getpass.GetPassWarning):
        raise ClientError("Authentication requires a terminal that hides input.") from None


def _emit(value: Any, *, pretty: bool = False, stream: bool = False) -> None:
    print(json.dumps(value, indent=2 if pretty else None), flush=stream)


def _terminal_text(text: str) -> str:
    return "".join(
        char for char in text if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf"}
    )


def _prompt(source: Path | None) -> str:
    if source is None and sys.stdin.isatty():
        print("Enter a prompt, then end input with EOF.", file=sys.stderr)
    try:
        if source is None or source == Path("-"):
            data = sys.stdin.buffer.read(MAX_PROMPT_BYTES + 1)
        else:
            with source.open("rb") as handle:
                data = handle.read(MAX_PROMPT_BYTES + 1)
        text = data.decode("utf-8")
    except (OSError, UnicodeError):
        raise ClientError("Prompt must be readable UTF-8.") from None
    if len(data) > MAX_PROMPT_BYTES or len(text) > MAX_PROMPT_CHARS or not text.strip():
        raise ClientError("Prompt is empty or exceeds the API input limit.")
    return text


def _watch(api: OwnerAPI, request_id: str, as_json: bool, after: str | None = None) -> int:
    path = f"/api/requests/{_segment(request_id)}/event-page"
    cursor = after
    while True:
        params = {"after": cursor} if cursor else None
        page = _parse(RequestEventPage, api.request("GET", path, params=params, retry=True))
        if page.has_more and (not page.events or page.next_cursor == cursor):
            raise ClientError("Orion request observation did not advance.")
        for event in page.events:
            if as_json:
                _emit({"kind": "event", **event.model_dump(mode="json")}, stream=True)
            elif event.type == "assistant.message":
                content = event.payload.get("content")
                if isinstance(content, str):
                    print(_terminal_text(content), flush=True)
            elif event.type == "tool.authorization_required":
                print(
                    "Command approval required. Inspect it with 'orion request payload'.",
                    file=sys.stderr,
                )
                _emit_to_stderr(event.payload)
        cursor = page.next_cursor or cursor
        if page.status not in ACTIVE and not page.has_more:
            if as_json:
                _emit(
                    {"kind": "status", "request_id": request_id, "status": page.status},
                    stream=True,
                )
            else:
                print(f"Request {page.status}.", file=sys.stderr)
            return EXIT_STATUS[page.status]
        if not page.has_more:
            time.sleep(0.15)


def _emit_to_stderr(value: Any) -> None:
    print(json.dumps(value), file=sys.stderr)


def _submit(api: OwnerAPI, args: argparse.Namespace, content: str) -> int:
    session_id = args.session
    if session_id is None:
        path = (
            f"/api/projects/{_segment(args.project)}/sessions" if args.project else "/api/sessions"
        )
        session = api.request("POST", path)
        if not isinstance(session, dict) or not isinstance(session.get("session_id"), str):
            raise ClientError("Orion returned an incompatible session response.")
        session_id = session["session_id"]
    path = f"/api/sessions/{_segment(session_id)}"
    client_key = str(args.client_request_id or uuid4())
    body = {"client_request_id": client_key, "content": content}
    identity = {"session_id": session_id, "client_request_id": client_key}
    if args.json:
        _emit({"kind": "submission", **identity}, stream=True)
    else:
        _emit_to_stderr(identity)
    try:
        view = _parse(RequestView, api.request("POST", path + "/requests", body=body, retry=True))
        if args.json:
            _emit({"kind": "admission", **view.model_dump(mode="json")}, stream=True)
        else:
            _emit_to_stderr({"request_id": view.request_id})
        return _watch(api, view.request_id, args.json)
    except KeyboardInterrupt:
        try:
            view = _parse(
                RequestView,
                api.request("POST", path + "/request-cancellations", body=body, retry=True),
            )
            if args.json:
                _emit({"kind": "cancellation", **view.model_dump(mode="json")}, stream=True)
            else:
                _emit_to_stderr({"request_id": view.request_id, "status": view.status})
        except ClientError as error:
            print(f"Cancellation could not be confirmed. {error}", file=sys.stderr)
        return 130


def _uuid4(value: str) -> UUID:
    try:
        parsed = UUID(value)
        if parsed.version == 4 and str(parsed) == value:
            return parsed
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Expected a canonical UUIDv4.")


def _parser(verb: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"orion {verb}")
    parser.add_argument("--server", default=os.environ.get("ORION_SERVER", DEFAULT_ORIGIN))
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--enroll", action="store_true", help="Prompt for a one-time native code.")
    auth.add_argument(
        "--login", action="store_true", help="Prompt for the owner password over HTTPS."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON or streaming JSON lines.")
    if verb in {"chat", "run"}:
        parser.add_argument("--prompt-file", type=Path, help="Read UTF-8 here instead of stdin.")
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument("--session")
        scope.add_argument("--project")
        parser.add_argument(
            "--client-request-id", type=_uuid4, help="Retry with the same session and prompt."
        )
    elif verb == "request":
        parser.add_argument(
            "action", choices=("status", "watch", "cancel", "payload", "allow", "deny")
        )
        parser.add_argument("id", metavar="REQUEST_ID")
        parser.add_argument("--after", type=_uuid4)
        parser.add_argument("--session")
        parser.add_argument("--call")
        parser.add_argument("--payload-hash")
    elif verb == "command":
        parser.add_argument("action", choices=("list", "status", "cancel"))
        parser.add_argument("id", metavar="COMMAND_ID", nargs="?")
        parser.add_argument("--session", required=True)
        parser.add_argument("--stdout-offset", type=int, default=0)
        parser.add_argument("--stderr-offset", type=int, default=0)
        parser.add_argument("--offset", type=int, default=0)
    elif verb == "profile":
        parser.add_argument("action", choices=("list", "activate", "create"))
        parser.add_argument("id", nargs="?")
        parser.add_argument("--input-file", type=Path)
    elif verb == "project":
        parser.add_argument("action", choices=("list", "show", "create"))
        parser.add_argument("id", nargs="?")
        parser.add_argument("--input-file", type=Path)
    elif verb == "session":
        parser.add_argument("action", choices=("list", "mode"))
        parser.add_argument("id", nargs="?")
        parser.add_argument("--mode", choices=tuple(mode.value for mode in MutationMode))
    elif verb == "api":
        parser.add_argument("resource", choices=("skill", "mcp"))
        parser.add_argument("action", choices=("list", "doctor", "test", "connect", "disconnect"))
        parser.add_argument("id", nargs="?")
        parser.add_argument("--session")
    return parser


def _operation(
    parser: argparse.ArgumentParser, verb: str, args: argparse.Namespace
) -> tuple[str, str, dict[str, Any] | None, dict[str, str | int] | None]:
    if verb in {"doctor", "target"}:
        return "GET", "/api/doctor" if verb == "doctor" else "/api/targets", None, None
    action, identity = args.action, args.id
    if verb == "api" and args.resource == "skill":
        if action != "list" or not args.session or identity:
            parser.error("Use 'api skill list --session SESSION_ID'.")
        return "GET", f"/api/sessions/{_segment(args.session)}/skills", None, None
    if verb in {"profile", "project"} and action == "create":
        if identity or not args.input_file:
            parser.error("Creation requires --input-file PATH (or - for stdin).")
        try:
            payload = json.loads(_prompt(args.input_file))
        except (ValueError, RecursionError):
            raise ClientError("Expected a JSON object in --input-file.") from None
        if not isinstance(payload, dict):
            raise ClientError("Expected a JSON object in --input-file.")
        return "POST", "/api/models" if verb == "profile" else "/api/projects", payload, None
    if verb in {"profile", "project"} and args.input_file:
        parser.error("--input-file is only valid for create.")
    if (action in {"list", "doctor"}) == bool(identity):
        parser.error("Provide a resource ID for this action only when required.")
    item = _segment(identity) if identity else ""
    if verb == "profile":
        if action == "activate":
            return "POST", f"/api/models/{item}/activate", None, None
        return "GET", "/api/models", None, None
    if verb == "project":
        return "GET", f"/api/projects/{item}" if item else "/api/projects", None, None
    if verb == "session":
        if action == "mode" and args.mode:
            return (
                "PATCH",
                f"/api/sessions/{item}/mutation-mode",
                {"mutation_mode": args.mode},
                None,
            )
        if action == "mode" or args.mode:
            parser.error("Specify --mode only with 'session mode SESSION_ID'.")
        return "GET", "/api/sessions", None, None
    if verb == "api":
        if args.session:
            parser.error("--session is only valid for skills.")
        if action in {"list", "doctor"}:
            return "GET", "/api/mcp/servers" if action == "list" else "/api/mcp/doctor", None, None
        return "POST", f"/api/mcp/servers/{item}/{action}", None, None
    if verb == "command":
        base = f"/api/sessions/{_segment(args.session)}/commands"
        if action == "list":
            return "GET", base, None, {"offset": args.offset}
        if action == "cancel":
            return "POST", f"{base}/{item}/cancel", None, None
        return (
            "GET",
            f"{base}/{item}",
            None,
            {
                "stdout_offset": args.stdout_offset,
                "stderr_offset": args.stderr_offset,
            },
        )
    if action in {"status", "watch", "cancel"}:
        if args.session or args.call or args.payload_hash or (args.after and action != "watch"):
            parser.error("Use --after with watch and authorization flags with payload/allow/deny.")
        if action == "cancel":
            return "POST", f"/api/requests/{item}/cancel", None, None
        return "GET", f"/api/requests/{item}", None, None
    if not args.session or not args.call or args.after:
        parser.error("Authorization requires --session and --call.")
    path = (
        f"/api/sessions/{_segment(args.session)}/requests/{item}"
        f"/tool-authorizations/{_segment(args.call)}"
    )
    if action == "payload":
        if args.payload_hash:
            parser.error("--payload-hash is only valid for an authorization decision.")
        return "GET", path + "/payload", None, None
    if not args.payload_hash:
        parser.error("Inspect the exact payload first and supply its --payload-hash.")
    return "POST", path, {"decision": action, "payload_hash": args.payload_hash}, None


def run_client_command(arguments: list[str]) -> None:
    verb = arguments[0]
    parser = _parser(verb)
    args = parser.parse_args(arguments[1:])
    submission = verb in {"chat", "run"}
    try:
        origin = _origin(args.server)
        if submission:
            if args.client_request_id and not args.session:
                parser.error("--client-request-id requires the original --session.")
            content = _prompt(args.prompt_file)
        else:
            method, path, body, params = _operation(parser, verb, args)
        with httpx.Client(
            follow_redirects=False,
            trust_env=False,
            timeout=5.0,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        ) as http:
            api = OwnerAPI(http, origin)
            api.identify()
            try:
                if args.enroll:
                    api.enroll()
                elif args.login:
                    api.login()
                if submission:
                    result = _submit(api, args, content)
                elif verb == "request" and args.action == "watch":
                    result = _watch(
                        api, args.id, args.json, str(args.after) if args.after else None
                    )
                else:
                    _emit(api.request(method, path, body=body, params=params), pretty=not args.json)
                    result = 0
            finally:
                api.close_session()
    except ClientError as error:
        print(error, file=sys.stderr)
        result = 1
    except KeyboardInterrupt:
        result = 130
    if result:
        raise SystemExit(result)
