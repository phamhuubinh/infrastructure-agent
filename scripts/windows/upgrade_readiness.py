"""Create or verify a Windows rollback snapshot from a source checkout."""

from orion.cli.upgrade_snapshot import (
    database_state,
    guarded_main,
    inventory,
    sha,
    verify,
)

__all__ = ["database_state", "inventory", "sha", "verify"]

if __name__ == "__main__":
    guarded_main()
