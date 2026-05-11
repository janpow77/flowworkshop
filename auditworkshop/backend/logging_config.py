"""Backwards-compatible Re-Export.

Die Logging-Implementierung wandert in das wiederverwendbare Paket
``cockpit_common.logging_setup``. Damit nutzen Workshop-Backend,
Cockpit-API und alle Folge-Anwendungen denselben Code (siehe
migration-log Beobachtung 6 zur künftigen Auslagerung als eigenes
PyPI-Paket ``cockpit-common``).
"""
from cockpit_common.logging_setup import (  # noqa: F401
    RequestContextMiddleware,
    configure_logging,
    current_actor,
    current_request_id,
)
