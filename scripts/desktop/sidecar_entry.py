"""Entrypoint for the application-owned backend executable."""

from orion.cli.managed import serve_managed

if __name__ == "__main__":
    serve_managed()
