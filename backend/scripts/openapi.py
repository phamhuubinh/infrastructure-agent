"""Generate or verify the backend-authoritative public OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from orion.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--path", type=Path, default=Path(__file__).parents[2] / "ui" / "openapi.json"
    )
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        app = create_app(Path(temporary) / "orion.db")
        try:
            expected = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
        finally:
            # Schema generation does not enter ASGI lifespan. Release SQLite
            # explicitly before Windows removes the temporary database folder.
            app.state.application.store.close()
    if arguments.write:
        arguments.path.write_text(expected, encoding="utf-8")
        return
    if not arguments.path.exists() or arguments.path.read_text(encoding="utf-8") != expected:
        raise SystemExit("OpenAPI contract drift: run `make openapi` and commit ui/openapi.json.")


if __name__ == "__main__":
    main()
