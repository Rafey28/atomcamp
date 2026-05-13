import json
import os
import uuid
from typing import Any, Optional
from threading import Lock


class JSONDatabase:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.lock = Lock()
        os.makedirs(self.data_dir, exist_ok=True)

    def _path(self, table: str) -> str:
        return os.path.join(self.data_dir, f"{table}.json")

    def _load(self, table: str) -> list[dict]:
        path = self._path(table)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, table: str, data: list[dict]) -> None:
        with open(self._path(table), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def all(self, table: str) -> list[dict]:
        with self.lock:
            return self._load(table)

    def find(self, table: str, **filters) -> list[dict]:
        return [r for r in self.all(table) if all(r.get(k) == v for k, v in filters.items())]

    def get(self, table: str, record_id: str) -> Optional[dict]:
        records = self.find(table, id=record_id)
        return records[0] if records else None

    def insert(self, table: str, record: dict) -> dict:
        with self.lock:
            data = self._load(table)
            if "id" not in record:
                record["id"] = str(uuid.uuid4())[:8]
            data.append(record)
            self._save(table, data)
            return record

    def update(self, table: str, record_id: str, updates: dict) -> Optional[dict]:
        with self.lock:
            data = self._load(table)
            for i, r in enumerate(data):
                if r.get("id") == record_id:
                    data[i] = {**r, **updates}
                    self._save(table, data)
                    return data[i]
            return None

    def delete(self, table: str, record_id: str) -> bool:
        with self.lock:
            data = self._load(table)
            new_data = [r for r in data if r.get("id") != record_id]
            if len(new_data) == len(data):
                return False
            self._save(table, new_data)
            return True

    def seed(self, table: str, records: list[dict]) -> None:
        with self.lock:
            if not os.path.exists(self._path(table)) or not self._load(table):
                self._save(table, records)

    def upsert(self, table: str, key_fields: dict, record: dict) -> dict:
        existing = self.find(table, **key_fields)
        if existing:
            return self.update(table, existing[0]["id"], record)
        return self.insert(table, {**key_fields, **record})

    def delete_where(self, table: str, **filters) -> int:
        with self.lock:
            data = self._load(table)
            kept = [r for r in data if not all(r.get(k) == v for k, v in filters.items())]
            removed = len(data) - len(kept)
            if removed:
                self._save(table, kept)
            return removed
