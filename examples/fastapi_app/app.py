from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_database_url(config_path: Path = CONFIG_PATH) -> str:
    config = json.loads(config_path.read_text())
    database_url = config.get("DATABASE_URL")
    if database_url is None:
        raise RuntimeError("DATABASE_URL missing")
    return database_url


def create_app(config_path: Path = CONFIG_PATH) -> FastAPI:
    app = FastAPI()
    app.state.database_url = load_database_url(config_path)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
