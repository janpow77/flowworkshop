"""Pydantic-Validator für migration.yaml (MIG-02, APPS_PREPARATION.md §8.1).

Definiert das Schema, das jede Anwendung mit ihrer migration.yaml
einhalten muss. Das Cockpit (Domäne 14, Umgebungsverwaltung) und das
zentrale `tools/migrate.py` parsen diese Datei und führen die Stufen
8.1 bis 8.7 darauf aus.

Beispiel:

    from cockpit_common.migration import load_migration_yaml
    manifest = load_migration_yaml("/opt/auditworkshop/migration.yaml")
    for entry in manifest.postgres:
        print(entry.schema, entry.classification)
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Classification(str, Enum):
    MITNEHMEN_TRANSFORMIERT = "mitnehmen-transformiert"
    MITNEHMEN_IDENTISCH = "mitnehmen-identisch"
    VERWERFEN = "verwerfen"
    NEU_ERZEUGEN = "neu-erzeugen"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostgresEntry(_Base):
    schema_: str = Field(..., alias="schema")
    classification: Classification
    rationale: str | None = None
    transform_steps: list[str] = []
    expected_size_mb: float | str | None = None
    consistency_checks: list[str] = []


class FilesystemEntry(_Base):
    path: str
    classification: Classification
    target_path: str | None = None
    rationale: str | None = None
    consistency_checks: list[str] = []


class VolumeEntry(_Base):
    name: str
    classification: Classification
    rationale: str | None = None


class ExternalConfigEntry(_Base):
    name: str
    classification: Classification
    rationale: str | None = None


class CategoryClassification(_Base):
    classification: Classification
    rationale: str | None = None


class Baseline(_Base):
    health_endpoint_status: Literal["ready", "degraded", "starting", "draining"] | None = None
    knowledge_chunks_total: int | str | None = None
    geocode_cache_entries: int | str | None = None
    registrations_count: int | str | None = None
    beneficiary_records_count: int | str | None = None


class MigrationManifest(_Base):
    """Vollständiges Manifest einer Anwendungs-Migration."""

    slug: str
    visibility: Literal["shared", "private"] = "shared"
    source_environment: str
    target_environment: Literal["production", "development"]

    postgres: list[PostgresEntry] = []
    filesystem: list[FilesystemEntry] = []
    volumes: list[VolumeEntry] = []
    external_config: list[ExternalConfigEntry] = []
    logs: CategoryClassification | None = None
    tracking: CategoryClassification | None = None
    baseline: Baseline | None = None


def load_migration_yaml(path: str | Path) -> MigrationManifest:
    """Liest die migration.yaml und validiert das Schema.

    Wirft `pydantic.ValidationError` bei Schema-Fehlern; `FileNotFoundError`
    bei fehlender Datei. Idempotent — kann beliebig oft aufgerufen werden.
    """
    import yaml  # type: ignore

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"migration.yaml fehlt unter {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return MigrationManifest.model_validate(raw)
