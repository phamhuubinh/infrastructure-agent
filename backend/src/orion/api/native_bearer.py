"""Native owner bearer boundary, evaluated before browser cookie/Origin checks."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send


class NativeBearerMiddleware:
    def __init__(
        self, app: ASGIApp, *, routes_app: FastAPI, protected_routes: set[tuple[str, str]]
    ) -> None:
        self.app, self.routes_app, self.protected_routes = app, routes_app, protected_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        classification = None
        for route in self.routes_app.routes:
            if isinstance(route, APIRoute):
                match, _ = route.matches(scope)
                if match == Match.FULL:
                    classification = (request.method, route.path)
                    break
        header = request.headers.get("authorization")
        if classification in self.protected_routes and header is not None:
            duplicate = sum(name.lower() == b"authorization" for name, _ in scope["headers"]) != 1
            scheme, _, token = header.partition(" ")
            application = getattr(self.routes_app.state, "application", None)
            identity = None
            if not duplicate and scheme.lower() == "bearer" and application is not None:
                identity = application.native_auth.authenticate(token)
            if (
                application is None
                or identity is None
                or identity[0] != application.access.current_principal()
            ):
                await JSONResponse(
                    {"detail": "Native credentials invalid or expired"},
                    status_code=401,
                    headers={"Cache-Control": "no-store", "X-Orion-Auth-Expired": "1"},
                )(scope, receive, send)
                return
            scope.setdefault("state", {})["native_session_id"] = identity[1]
            scope["state"]["native_authenticated"] = True
        await self.app(scope, receive, send)
