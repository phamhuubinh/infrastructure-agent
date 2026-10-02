"""Native Windows / X11 capture and input; unavailable environments fail closed."""

from __future__ import annotations

import base64
import io
import os
import sys
from typing import Any

from orion_endpoint.policy import Policy


class Desktop:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def available(self) -> bool:
        return sys.platform == "win32" or (
            sys.platform.startswith("linux")
            and bool(os.getenv("DISPLAY"))
            and not os.getenv("WAYLAND_DISPLAY")
            and os.getenv("XDG_SESSION_TYPE") != "wayland"
        )

    def _check(self) -> None:
        if not self.available():
            raise RuntimeError("unavailable")
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            api = ctypes.WinDLL("user32", use_last_error=True)
            api.OpenInputDesktop.restype = wintypes.HANDLE
            api.CloseDesktop.argtypes = [wintypes.HANDLE]
            api.GetUserObjectInformationW.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
            ]
            handle = api.OpenInputDesktop(0, False, 1)
            if not handle:
                raise RuntimeError("unavailable")
            try:
                name = ctypes.create_unicode_buffer(256)
                needed = wintypes.DWORD()
                if (
                    not api.GetUserObjectInformationW(
                        handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed)
                    )
                    or name.value.lower() != "default"
                ):
                    raise RuntimeError("unavailable")
            finally:
                api.CloseDesktop(handle)

    def geometry(self) -> list[dict[str, int]]:
        if not (self.policy.desktop_capture or self.policy.desktop_control):
            return []
        self._check()
        import mss

        with mss.mss() as screen:
            return [dict(monitor) for monitor in screen.monitors[1:17]]

    def capture(self, monitor: int) -> dict[str, Any]:
        if not self.policy.desktop_capture:
            raise PermissionError("policy_denied")
        self._check()
        import mss
        from PIL import Image

        with mss.mss() as screen:
            if monitor >= len(screen.monitors):
                raise ValueError("invalid_input")
            geometry = dict(screen.monitors[monitor])
            if geometry["width"] * geometry["height"] > 40_000_000:
                raise RuntimeError("unavailable")
            frame = screen.grab(screen.monitors[monitor])
            image = Image.frombytes("RGB", frame.size, frame.rgb)
        image.thumbnail((self.policy.max_resolution, self.policy.max_resolution))
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=65)
        if stream.tell() > 900_000:
            raise RuntimeError("unavailable")
        return {
            "image_b64": base64.b64encode(stream.getvalue()).decode(),
            "media_type": "image/jpeg",
            "width": image.width,
            "height": image.height,
            "geometry": geometry,
            "monitors": self.geometry(),
            "max_fps": self.policy.max_fps,
        }

    def input(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.policy.desktop_control:
            raise PermissionError("policy_denied")
        self._check()
        from pynput import keyboard, mouse

        pointer = mouse.Controller()
        if operation in {"click", "move"}:
            geometry = self.geometry()
            index = arguments["monitor"] - 1
            if index >= len(geometry):
                raise ValueError("invalid_input")
            display = geometry[index]
            x, y = arguments["x"], arguments["y"]
            if x >= display["width"] or y >= display["height"]:
                raise ValueError("invalid_input")
            pointer.position = (display["left"] + x, display["top"] + y)
            if operation == "click":
                pointer.click(getattr(mouse.Button, arguments["button"]))
        elif operation == "scroll":
            pointer.scroll(arguments["dx"], arguments["dy"])
        else:
            controller = keyboard.Controller()
            if operation == "type":
                controller.type(arguments["text"])
            else:
                name = arguments["key"]
                key = getattr(keyboard.Key, name, name)
                controller.press(key)
                controller.release(key)
        return {"applied": True}
