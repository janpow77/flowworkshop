"""
Alembic-Umgebung fuer das auditworkshop-Backend.

Besonderheiten dieses Projekts:
- Die DB-URL kommt aus ``config.DATABASE_URL`` (bzw. der Umgebungsvariable
  ``DATABASE_URL``), NICHT aus der alembic.ini.
- Neben den SQLAlchemy-Modellen (``Base.metadata``) existieren in derselben
  Datenbank Tabellen, die per rohem psycopg2 angelegt werden (pgvector /
  Wissensbasis in ``services/knowledge_service.py``). Auf CCX23-Prod ist es
  zudem ein *geteilter* Postgres mit weiteren Datenbanken/Tabellen.
  Deshalb verwaltet Alembic ausschliesslich Tabellen, die in
  ``Base.metadata`` bekannt sind (siehe ``include_object``) — fremde Tabellen
  werden bei ``autogenerate`` weder veraendert noch geloescht.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Projektpfad / Modelle laden -------------------------------------------
# prepend_sys_path = . in alembic.ini stellt sicher, dass das backend-Verzeichnis
# (mit config.py, database.py, models/) importierbar ist.
from config import DATABASE_URL  # noqa: E402
from database import Base  # noqa: E402
import models  # noqa: F401,E402  -> registriert alle Tabellen auf Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DB-URL zur Laufzeit setzen (kein Klartext-Secret in der ini).
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata

# Spezial-Indizes, die NICHT von SQLAlchemy-Modellen, sondern zur Laufzeit per
# rohem SQL angelegt werden (GIN/Trigram/IVFFlat/partielle Indizes in den
# knowledge-/state_aid-/sanctions-/beneficiary-Services). Alembic darf sie weder
# anlegen noch droppen — insbesondere der pgvector-IVFFlat-Index
# ``ix_entity_embedding_cosine`` ist betriebskritisch.
APP_MANAGED_INDEXES = {
    "ix_beneficiary_name_trgm",
    "ix_entity_embedding_cosine",
    "ix_entity_name_trgm",
    "ix_sanctions_aliases_gin",
    "ix_sanctions_name_trgm",
    "ix_state_aid_authority_trgm",
    "ix_state_aid_name_trgm",
    "ix_state_aid_nuts_prefix_pattern",
}


def include_object(obj, name, type_, reflected, compare_to):
    """Nur von SQLAlchemy verwaltete Objekte anfassen.

    Schuetzt (1) pgvector-/Wissensbasis- und dynamische ``workshop_df_*``-Tabellen
    (raw psycopg2) sowie fremde Tabellen auf dem geteilten Prod-Postgres, und
    (2) die app-verwalteten Spezial-Indizes vor versehentlichem DROP/ALTER durch
    ``autogenerate``.
    """
    if type_ == "table":
        return name in target_metadata.tables
    if type_ == "index" and name in APP_MANAGED_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    """Migrationen im 'offline'-Modus (nur SQL erzeugen)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrationen im 'online'-Modus (gegen eine echte Verbindung)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
