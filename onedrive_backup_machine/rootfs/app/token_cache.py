"""Persistent MSAL token cache stored under the add-on data directory."""
from __future__ import annotations

import json
from pathlib import Path

from msal import SerializableTokenCache


class FileTokenCache(SerializableTokenCache):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        if self._path.exists():
            self.deserialize(self._path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self.serialize(), encoding="utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
