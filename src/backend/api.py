import os

from src.backend.app import create_app

_db_url = os.environ.get("ORION_DATABASE_URL")
_target_store_path = os.environ.get("ORION_TARGETS_FILE", "targets.json")
app, _, _ = create_app(
    database_url=_db_url,
    target_store_path=_target_store_path,
)
