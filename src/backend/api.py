import os

from src.backend.app import create_app

_db_url = os.environ.get("ORION_DATABASE_URL")
app, _, _ = create_app(database_url=_db_url)
