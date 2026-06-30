"""Registry-source seam: where registry_search reads records from.

The capability registry lives in the separate Ycarus-12/registry repo. In dev/test
the orchestrator reads it from a local checkout (path via REGISTRY_PATH); tests use
the in-memory fake. Keeps the seam — production mounts the registry without code
changes.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

import yaml


class RegistrySource(ABC):
    @abstractmethod
    def records(self) -> list[dict]: ...


class InMemoryRegistry(RegistrySource):
    """Offline fake; records supplied directly (used by tests and eval mocks)."""

    def __init__(self, records: list[dict] | None = None) -> None:
        self._records = list(records or [])

    def records(self) -> list[dict]:
        return list(self._records)


class FilesystemRegistry(RegistrySource):
    """Reads one YAML record per file from a registry checkout's records/ tree."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def records(self) -> list[dict]:
        records_dir = self.root / "records"
        base = records_dir if records_dir.exists() else self.root
        out: list[dict] = []
        for path in sorted(base.rglob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "capabilities" in data:
                out.append(data)
        return out


def default_registry_source() -> RegistrySource:
    """FilesystemRegistry at REGISTRY_PATH if set, else an empty in-memory registry."""
    path = os.environ.get("REGISTRY_PATH")
    return FilesystemRegistry(path) if path else InMemoryRegistry([])
