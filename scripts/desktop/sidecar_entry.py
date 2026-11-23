"""Entrypoint for the application-owned backend executable."""

import sys

from orion.cli.managed import serve_managed

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--snapshot-for-update":
        from orion.cli.upgrade_snapshot import snapshot_for_update

        snapshot_for_update(sys.argv[2])
    else:
        serve_managed()
