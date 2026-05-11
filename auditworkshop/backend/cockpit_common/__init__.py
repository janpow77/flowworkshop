"""cockpit_common — wiederverwendbare Bausteine für alle Cockpit-Apps.

Wird als Sub-Package in jedem App-Backend mitgeführt, später als
eigenes PyPI-Paket / Git-Submodul ausgegliedert. Dieselbe Codebasis
liegt synchron unter `cockpit/api/cockpit_common/` und in jedem
Folge-Repo (audit_designer etc.).

Module:
    health           Health-Endpoint nach APPS_PREPARATION.md §2.2
                     mit Subcheck-Registry.
    logging_setup    JSON-Logging mit Pflichtfeldern + Request-Context.
    audit            Audit-Trail-Middleware für schreibende Methoden.
    production_mode  Production-Mode-Toggle als zweite Schutzschicht.
    migration        Pydantic-Validator für migration.yaml.
"""
from .health import HealthRegistry, build_health_handler, SubcheckResult
from .logging_setup import (
    RequestContextMiddleware,
    configure_logging,
    current_actor,
    current_request_id,
)
from .audit import AuditTrailMiddleware, AuditEntry, AuditWriter
from .production_mode import ProductionMode, require_production_mode
from .migration import (
    MigrationManifest,
    PostgresEntry,
    FilesystemEntry,
    VolumeEntry,
    Classification,
    load_migration_yaml,
)

__version__ = "0.1.0"

__all__ = [
    "HealthRegistry",
    "build_health_handler",
    "SubcheckResult",
    "RequestContextMiddleware",
    "configure_logging",
    "current_actor",
    "current_request_id",
    "AuditTrailMiddleware",
    "AuditEntry",
    "AuditWriter",
    "ProductionMode",
    "require_production_mode",
    "MigrationManifest",
    "PostgresEntry",
    "FilesystemEntry",
    "VolumeEntry",
    "Classification",
    "load_migration_yaml",
]
