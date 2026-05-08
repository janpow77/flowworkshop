"""
flowworkshop · main.py
FastAPI-Anwendung — Startup, CORS, Router-Registrierung.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from services.knowledge_service import init_db
from services.ollama_service import check_ollama, warmup_gateway_model
from routers import workshop, knowledge, system
from routers import projects, checklists, assessment, demo_data, dataframes, beneficiaries, reference_data, event, documents, auth, sanctions, forum, automation
from routers import docs as docs_router, notifications, state_aid, admin_access
from routers import beneficiaries_sources
from routers import entities as entities_router
from routers import embeddings as embeddings_router
from services.access_log_middleware import AccessLogMiddleware

# Modelle importieren damit Base.metadata sie kennt
import models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────
    log.info("flowworkshop startet …")

    # SQLAlchemy-Tabellen erstellen (workshop_*)
    try:
        Base.metadata.create_all(bind=engine)
        log.info("SQLAlchemy-Tabellen erstellt/geprueft.")
        # Access-Log: Behaltedauer-Hinweis (Pruning laeuft im Scheduler)
        from services.scheduler import WORKSHOP_ACCESS_LOG_TTL_DAYS as _ACL_TTL
        log.info(
            "Access-Log: Behaltedauer %d Tage; aelter wird taeglich geloescht.",
            _ACL_TTL,
        )
        # Uebergangsweise: fehlende Spalten fuer bestehende Workshop-DBs nachziehen.
        from sqlalchemy import text, inspect
        with engine.connect() as conn:
            inspector = inspect(engine)
            cols = [c["name"] for c in inspector.get_columns("workshop_agenda_items")]
            if "page_url" not in cols:
                conn.execute(text("ALTER TABLE workshop_agenda_items ADD COLUMN page_url VARCHAR(500)"))
                conn.commit()
                log.info("Spalte page_url zu workshop_agenda_items hinzugefuegt.")
            # Phase 4: Material-Verknüpfung
            agenda_extra = {
                "related_thread_ids": "ALTER TABLE workshop_agenda_items ADD COLUMN related_thread_ids JSON",
                "related_file_ids": "ALTER TABLE workshop_agenda_items ADD COLUMN related_file_ids JSON",
                "notes_md": "ALTER TABLE workshop_agenda_items ADD COLUMN notes_md TEXT",
            }
            for col, ddl in agenda_extra.items():
                if col not in cols:
                    conn.execute(text(ddl))
                    conn.commit()
                    log.info("Spalte %s zu workshop_agenda_items hinzugefuegt.", col)
            meta_cols = [c["name"] for c in inspector.get_columns("workshop_meta")]
            meta_migrations = {
                "phase": "ALTER TABLE workshop_meta ADD COLUMN phase VARCHAR(8) NOT NULL DEFAULT 'live'",
                "archive_started_at": "ALTER TABLE workshop_meta ADD COLUMN archive_started_at TIMESTAMP",
            }
            for col, ddl in meta_migrations.items():
                if col not in meta_cols:
                    conn.execute(text(ddl))
                    conn.commit()
                    log.info("Spalte %s zu workshop_meta hinzugefuegt.", col)
            reg_cols = [c["name"] for c in inspector.get_columns("workshop_registrations")]
            registration_migrations = {
                "password_hash": "ALTER TABLE workshop_registrations ADD COLUMN password_hash VARCHAR(255)",
                "password_updated_at": "ALTER TABLE workshop_registrations ADD COLUMN password_updated_at TIMESTAMP",
                "last_login_at": "ALTER TABLE workshop_registrations ADD COLUMN last_login_at TIMESTAMP",
                "qr_login_secret": "ALTER TABLE workshop_registrations ADD COLUMN qr_login_secret VARCHAR(128)",
                "qr_secret_rotated_at": "ALTER TABLE workshop_registrations ADD COLUMN qr_secret_rotated_at TIMESTAMP",
                # Phase-0-Erweiterung (Plan v3.2)
                "role": "ALTER TABLE workshop_registrations ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'attendee'",
                "status": "ALTER TABLE workshop_registrations ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'",
                "bundesland": "ALTER TABLE workshop_registrations ADD COLUMN bundesland VARCHAR(64)",
                "function_role": "ALTER TABLE workshop_registrations ADD COLUMN function_role VARCHAR(80)",
                "signup_reason": "ALTER TABLE workshop_registrations ADD COLUMN signup_reason TEXT",
                "avatar_path": "ALTER TABLE workshop_registrations ADD COLUMN avatar_path VARCHAR(255)",
                "quota_bytes": "ALTER TABLE workshop_registrations ADD COLUMN quota_bytes BIGINT NOT NULL DEFAULT 209715200",
                "used_bytes": "ALTER TABLE workshop_registrations ADD COLUMN used_bytes BIGINT NOT NULL DEFAULT 0",
                "rejection_reason": "ALTER TABLE workshop_registrations ADD COLUMN rejection_reason TEXT",
                "approved_at": "ALTER TABLE workshop_registrations ADD COLUMN approved_at TIMESTAMP",
                "approved_by_id": "ALTER TABLE workshop_registrations ADD COLUMN approved_by_id VARCHAR(36)",
                "deleted_at": "ALTER TABLE workshop_registrations ADD COLUMN deleted_at TIMESTAMP",
            }
            for col, ddl in registration_migrations.items():
                if col not in reg_cols:
                    conn.execute(text(ddl))
                    conn.commit()
                    log.info("Spalte %s zu workshop_registrations hinzugefuegt.", col)

            # Spalte edit_count: Default-Backfill, falls Migration aus
            # früherem Run schon lief, aber server_default fehlte
            try:
                conn.execute(text("ALTER TABLE workshop_forum_posts ALTER COLUMN edit_count SET DEFAULT 0"))
                conn.execute(text("UPDATE workshop_forum_posts SET edit_count = 0 WHERE edit_count IS NULL"))
                conn.commit()
            except Exception:
                pass

            # Forum-Kategorien initial befüllen, wenn leer (Plan v3.2 §6)
            cat_count = conn.execute(text("SELECT COUNT(*) FROM workshop_forum_categories")).scalar()
            thread_count = conn.execute(text("SELECT COUNT(*) FROM workshop_forum_threads")).scalar()
            legacy_count = conn.execute(text("SELECT COUNT(*) FROM workshop_agenda_forum_posts")).scalar()
            need_migration = (thread_count == 0 and legacy_count > 0)
            if cat_count == 0:
                default_categories = [
                    ("allgemein", "Allgemein", "Themen ohne festen Programmpunkt", "MessagesSquare", "slate", 0),
                    ("workshop-2026", "Workshop 2026 (Live-Diskussionen)", "Beiträge der Veranstaltung im Mai 2026", "Calendar", "cyan", 10),
                    ("ki-pruefung", "KI in der Prüfung", "Erfahrungen, Use-Cases, offene Fragen", "Sparkles", "violet", 20),
                    ("methodik", "Methodik & Stichprobenprüfung", "MUS, SRS, Differenzenschätzung", "Calculator", "emerald", 30),
                    ("rechtsfragen", "Rechtsfragen", "VO, Förderrichtlinien, Auslegung", "Scale", "amber", 40),
                    ("plattform", "Plattform-Feedback", "Was funktioniert, was fehlt", "Wrench", "indigo", 50),
                ]
                for slug, name, desc, icon, color, sort in default_categories:
                    conn.execute(text(
                        "INSERT INTO workshop_forum_categories (id, slug, name, description, icon, color, sort_order, archived) "
                        "VALUES (gen_random_uuid()::text, :s, :n, :d, :i, :c, :o, false)"
                    ), {"s": slug, "n": name, "d": desc, "i": icon, "c": color, "o": sort})
                conn.commit()
                log.info("Forum: %d Default-Kategorien angelegt.", len(default_categories))
                need_migration = True

            if need_migration:
                # Migration: bestehende AgendaForumPost → forum_threads/forum_posts
                # in Kategorie 'workshop-2026', gruppiert nach agenda_item_id
                workshop_cat = conn.execute(text(
                    "SELECT id FROM workshop_forum_categories WHERE slug = 'workshop-2026'"
                )).scalar()
                if workshop_cat:
                    legacy_posts = conn.execute(text(
                        "SELECT p.id, p.agenda_item_id, p.title, p.body, "
                        "p.author_registration_id, p.author_name, p.author_organization, "
                        "p.created_at, a.title AS item_title "
                        "FROM workshop_agenda_forum_posts p "
                        "LEFT JOIN workshop_agenda_items a ON a.id = p.agenda_item_id "
                        "ORDER BY p.created_at ASC"
                    )).fetchall()
                    threads_by_item: dict = {}
                    for row in legacy_posts:
                        agenda_id = row.agenda_item_id
                        if agenda_id not in threads_by_item:
                            t_slug = "tag-" + agenda_id[:8]
                            t_title = row.item_title or "Workshop-Diskussion"
                            new_thread_id = conn.execute(text(
                                "INSERT INTO workshop_forum_threads "
                                "(id, slug, category_id, title, body_md, author_user_id, "
                                "author_name, author_organization, created_at, last_post_at, "
                                "post_count, view_count, pinned, locked, agenda_item_id) "
                                "VALUES (gen_random_uuid()::text, :s, :c, :t, :b, :u, :n, :o, :ts, :ts, 0, 0, false, false, :a) "
                                "RETURNING id"
                            ), {
                                "s": t_slug, "c": workshop_cat, "t": t_title,
                                "b": row.body or "", "u": row.author_registration_id,
                                "n": row.author_name, "o": row.author_organization,
                                "ts": row.created_at, "a": agenda_id,
                            }).scalar()
                            threads_by_item[agenda_id] = new_thread_id
                        thread_id = threads_by_item[agenda_id]
                        conn.execute(text(
                            "INSERT INTO workshop_forum_posts "
                            "(id, thread_id, author_user_id, author_name, author_organization, "
                            "body_md, created_at) "
                            "VALUES (gen_random_uuid()::text, :tid, :u, :n, :o, :b, :ts)"
                        ), {
                            "tid": thread_id, "u": row.author_registration_id,
                            "n": row.author_name, "o": row.author_organization,
                            "b": (row.title + "\n\n" + (row.body or "")) if row.title else (row.body or ""),
                            "ts": row.created_at,
                        })
                    # post_count + last_post_at je Thread aktualisieren
                    conn.execute(text("""
                        UPDATE workshop_forum_threads t
                           SET post_count = (SELECT COUNT(*) FROM workshop_forum_posts p WHERE p.thread_id = t.id),
                               last_post_at = COALESCE(
                                   (SELECT MAX(created_at) FROM workshop_forum_posts p WHERE p.thread_id = t.id),
                                   t.created_at
                               )
                    """))
                    conn.commit()
                    log.info(
                        "Forum-Migration: %d Threads aus %d AgendaForumPost erzeugt.",
                        len(threads_by_item), len(legacy_posts),
                    )

            # Default-Ordner für Dokumente-Bereich (Plan v3.2 §7)
            doc_count = conn.execute(text("SELECT COUNT(*) FROM workshop_doc_folders")).scalar()
            if doc_count == 0:
                default_folders = [
                    # name, slug, description, visibility, upload_policy, is_shared_pool, icon, sort
                    ("Workshop-Material 2026", "workshop-material-2026", "Folien, Templates, Aufzeichnungen", "public_read", "moderators", False, "FolderArchive", 0),
                    ("Templates & Vorlagen", "templates", "CL, Berichte, Anschreiben", "members_read", "moderators", False, "FileText", 10),
                    ("Auswertungen", "auswertungen", "Berichte, Statistiken, Stichproben-Auswertungen", "members_read", "moderators", False, "BarChart", 20),
                    ("Rechtsgrundlagen", "rechtsgrundlagen", "Verordnungen, Richtlinien, Erlasse", "public_read", "moderators", False, "Scale", 30),
                    ("Geteilt von Teilnehmern", "geteilt", "Eigene Dateien aller Mitglieder mit Bundesland-Filter", "members_read", "members", True, "Users", 100),
                ]
                for name, slug, desc, vis, pol, shared, icon, sort in default_folders:
                    conn.execute(text(
                        "INSERT INTO workshop_doc_folders (id, name, slug, description, visibility, upload_policy, is_shared_pool, icon, sort_order) "
                        "VALUES (gen_random_uuid()::text, :n, :s, :d, :v, :p, :sh, :i, :o)"
                    ), {"n": name, "s": slug, "d": desc, "v": vis, "p": pol, "sh": shared, "i": icon, "o": sort})
                conn.commit()
                log.info("Documents: %d Default-Ordner angelegt.", len(default_folders))
            # Storage-Verzeichnis sicherstellen
            from pathlib import Path as _P
            _P("/app/data/documents").mkdir(parents=True, exist_ok=True)
            _P("/app/data/documents/_trash").mkdir(parents=True, exist_ok=True)

            # Audit-Report-Log: aktenzeichen-Spalte entfernen (Mai 2026 —
            # Pruefer-Aktenzeichen wurde aus dem Bericht ganz herausgenommen).
            # Idempotent — DROP COLUMN IF EXISTS gibt es ab PG 9.x.
            try:
                conn.execute(text(
                    "ALTER TABLE workshop_audit_report_log "
                    "DROP COLUMN IF EXISTS aktenzeichen"
                ))
                conn.commit()
            except Exception as e:
                log.warning("Audit-Report-Log aktenzeichen-Drop fehlgeschlagen: %s", e)

            # State-Aid-Migrations (idempotent, Plan §11 Smart-Mode)
            try:
                sa_run_cols = [
                    c["name"] for c in inspector.get_columns(
                        "workshop_state_aid_harvest_runs",
                    )
                ]
                if "records_skipped" not in sa_run_cols:
                    conn.execute(text(
                        "ALTER TABLE workshop_state_aid_harvest_runs "
                        "ADD COLUMN records_skipped INTEGER DEFAULT 0"
                    ))
                    conn.commit()
                    log.info(
                        "Spalte records_skipped zu "
                        "workshop_state_aid_harvest_runs hinzugefuegt.",
                    )
            except Exception as e:
                log.warning("State-Aid records_skipped-Migration fehlgeschlagen: %s", e)

            # State-Aid-Sources: expected_total + expected_total_updated_at
            # fuer Coverage-Sektion (Polish-Runde 3, Aufgabe 3).
            try:
                sa_src_cols = [
                    c["name"] for c in inspector.get_columns(
                        "workshop_state_aid_sources",
                    )
                ]
                if "expected_total" not in sa_src_cols:
                    conn.execute(text(
                        "ALTER TABLE workshop_state_aid_sources "
                        "ADD COLUMN expected_total INTEGER"
                    ))
                    conn.commit()
                    log.info(
                        "Spalte expected_total zu workshop_state_aid_sources "
                        "hinzugefuegt (Coverage-Sektion).",
                    )
                if "expected_total_updated_at" not in sa_src_cols:
                    conn.execute(text(
                        "ALTER TABLE workshop_state_aid_sources "
                        "ADD COLUMN expected_total_updated_at TIMESTAMP"
                    ))
                    conn.commit()
                    log.info(
                        "Spalte expected_total_updated_at zu "
                        "workshop_state_aid_sources hinzugefuegt.",
                    )
            except Exception as e:
                log.warning(
                    "State-Aid expected_total-Migration fehlgeschlagen: %s", e,
                )

            # Sanctions Multi-Source: Migration der neuen Spalten
            # (sources, parameters JSON) auf workshop_sanctions_refresh.
            # Idempotent.
            try:
                sanctions_run_cols = [
                    c["name"] for c in inspector.get_columns(
                        "workshop_sanctions_refresh",
                    )
                ]
                if "sources" not in sanctions_run_cols:
                    conn.execute(text(
                        "ALTER TABLE workshop_sanctions_refresh "
                        "ADD COLUMN sources VARCHAR(255)"
                    ))
                    conn.commit()
                    log.info(
                        "Spalte sources zu workshop_sanctions_refresh "
                        "hinzugefuegt (Multi-Source-Refresh).",
                    )
                if "parameters" not in sanctions_run_cols:
                    conn.execute(text(
                        "ALTER TABLE workshop_sanctions_refresh "
                        "ADD COLUMN parameters JSON"
                    ))
                    conn.commit()
                    log.info(
                        "Spalte parameters zu workshop_sanctions_refresh "
                        "hinzugefuegt (Per-Source-Subreport).",
                    )
            except Exception as e:
                log.warning(
                    "Sanctions-Refresh Multi-Source-Migration fehlgeschlagen: %s", e,
                )

            # Phase 6c: Sanctions-Schema-Normalisierung — eine Tabelle fuer alle
            # 5 Sanctions-Listen. Wir legen Indizes auf workshop_sanctions_entries
            # an (pg_trgm wird unten fuer State-Aid eh angelegt; CREATE EXTENSION
            # ist idempotent):
            #   - GIN trgm auf name_normalized (Fuzzy-ILIKE-Vorfilter)
            #   - GIN auf aliases JSONB (Containment-Suche)
            #
            # Zusaetzlich: Migration fuer aelter angelegte Tabellen, in denen
            # birth_date/first_seen/last_seen noch VARCHAR(40) sind. Bei
            # Multi-Birth-Date-Eintraegen reicht das nicht (OpenSanctions
            # liefert semikolongetrennte Listen mit > 40 Zeichen). Idempotent
            # ueber ALTER COLUMN ... TYPE TEXT.
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
                # Vorab: eventuelle VARCHAR(40)-Spalten auf TEXT migrieren.
                varchar_cols = {
                    c["name"]: str(c.get("type"))
                    for c in inspector.get_columns("workshop_sanctions_entries")
                }
                for col in ("birth_date", "first_seen", "last_seen"):
                    coltype = (varchar_cols.get(col) or "").upper()
                    if coltype.startswith("VARCHAR"):
                        try:
                            conn.execute(text(
                                f"ALTER TABLE workshop_sanctions_entries "
                                f"ALTER COLUMN {col} TYPE TEXT"
                            ))
                            conn.commit()
                            log.info(
                                "Spalte %s in workshop_sanctions_entries "
                                "von %s auf TEXT migriert.",
                                col, coltype,
                            )
                        except Exception as alter_exc:
                            log.warning(
                                "ALTER COLUMN %s fehlgeschlagen: %s",
                                col, alter_exc,
                            )
                sanctions_entry_idx = [
                    i["name"] for i in inspector.get_indexes(
                        "workshop_sanctions_entries",
                    )
                ]
                if "ix_sanctions_name_trgm" not in sanctions_entry_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_sanctions_name_trgm "
                        "ON workshop_sanctions_entries "
                        "USING GIN (name_normalized gin_trgm_ops)"
                    ))
                    conn.commit()
                    log.info(
                        "pg_trgm-Index ix_sanctions_name_trgm auf "
                        "workshop_sanctions_entries(name_normalized) angelegt.",
                    )
                if "ix_sanctions_aliases_gin" not in sanctions_entry_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_sanctions_aliases_gin "
                        "ON workshop_sanctions_entries "
                        "USING GIN (aliases)"
                    ))
                    conn.commit()
                    log.info(
                        "GIN-Index ix_sanctions_aliases_gin auf "
                        "workshop_sanctions_entries(aliases JSONB) angelegt.",
                    )
            except Exception as e:
                log.warning(
                    "Sanctions-Entries Index-Migration fehlgeschlagen: %s", e,
                )

            # State-Aid Phase 3: NUTS-Prefix-Indizes fuer schnelle Prefix-Suche
            # auf wachsendem Bestand (170k+ Records). Idempotent via
            # CREATE INDEX IF NOT EXISTS.
            try:
                sa_award_idx = [
                    i["name"] for i in inspector.get_indexes(
                        "workshop_state_aid_awards",
                    )
                ]
                if "ix_state_aid_nuts_prefix" not in sa_award_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_state_aid_nuts_prefix "
                        "ON workshop_state_aid_awards (nuts_code) "
                        "WHERE nuts_code IS NOT NULL"
                    ))
                    conn.commit()
                    log.info("Index ix_state_aid_nuts_prefix angelegt.")
                if "ix_state_aid_country_nuts" not in sa_award_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_state_aid_country_nuts "
                        "ON workshop_state_aid_awards (country_code, nuts_code)"
                    ))
                    conn.commit()
                    log.info("Index ix_state_aid_country_nuts angelegt.")
                # Zusatz: text_pattern_ops-Index, damit LIKE 'DE2%' den
                # Index nutzen kann (Standard-Locale-Indizes helfen Postgres
                # bei LIKE-Prefix-Match nicht). Idempotent via IF NOT EXISTS.
                if "ix_state_aid_nuts_prefix_pattern" not in sa_award_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_state_aid_nuts_prefix_pattern "
                        "ON workshop_state_aid_awards (nuts_code text_pattern_ops) "
                        "WHERE nuts_code IS NOT NULL"
                    ))
                    conn.commit()
                    log.info("Index ix_state_aid_nuts_prefix_pattern angelegt.")
            except Exception as e:
                log.warning("State-Aid NUTS-Index-Migration fehlgeschlagen: %s", e)

            # State-Aid Search-Optimierung: pg_trgm-Extension + GIN-Indizes
            # auf beneficiary_name_normalized + granting_authority. Damit
            # wird das tokenweise ILIKE '%token%' im Fuzzy-Vorfilter aus
            # dem Seq Scan herausgehoben (170k+ Records → Bitmap Index Scan).
            # Idempotent.
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
                sa_award_idx = [
                    i["name"] for i in inspector.get_indexes(
                        "workshop_state_aid_awards",
                    )
                ]
                if "ix_state_aid_name_trgm" not in sa_award_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_state_aid_name_trgm "
                        "ON workshop_state_aid_awards "
                        "USING GIN (beneficiary_name_normalized gin_trgm_ops)"
                    ))
                    conn.commit()
                    log.info(
                        "pg_trgm-Index ix_state_aid_name_trgm auf "
                        "beneficiary_name_normalized angelegt."
                    )
                if "ix_state_aid_authority_trgm" not in sa_award_idx:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_state_aid_authority_trgm "
                        "ON workshop_state_aid_awards "
                        "USING GIN (granting_authority gin_trgm_ops) "
                        "WHERE granting_authority IS NOT NULL"
                    ))
                    conn.commit()
                    log.info(
                        "pg_trgm-Index ix_state_aid_authority_trgm auf "
                        "granting_authority angelegt."
                    )
            except Exception as e:
                log.warning("pg_trgm-Index konnte nicht angelegt werden: %s", e)

            # Phase 6a: pg_trgm-Index auf workshop_beneficiary_records.
            # Beschleunigt das ILIKE '%token%'-Vorfilter im Beneficiary-Search,
            # analog zu State-Aid (siehe oben). Idempotent.
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
                # Tabelle existiert ggf. noch nicht beim ersten Start vor
                # Base.metadata.create_all — wird per inspect geprueft.
                if inspector.has_table("workshop_beneficiary_records"):
                    bf_idx = [
                        i["name"] for i in inspector.get_indexes(
                            "workshop_beneficiary_records",
                        )
                    ]
                    if "ix_beneficiary_name_trgm" not in bf_idx:
                        conn.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_beneficiary_name_trgm "
                            "ON workshop_beneficiary_records "
                            "USING GIN (beneficiary_name_normalized gin_trgm_ops)"
                        ))
                        conn.commit()
                        log.info(
                            "pg_trgm-Index ix_beneficiary_name_trgm auf "
                            "beneficiary_name_normalized angelegt."
                        )
            except Exception as e:
                log.warning(
                    "Beneficiary pg_trgm-Index konnte nicht angelegt werden: %s",
                    e,
                )

            # Phase 6d: pg_trgm-Index auf workshop_company_entities — Master-
            # Tabelle der Entity-Resolution. Beschleunigt den ILIKE-Vorfilter
            # in services/entity_resolution._find_by_name_fuzzy. Idempotent.
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
                if inspector.has_table("workshop_company_entities"):
                    ce_idx = [
                        i["name"] for i in inspector.get_indexes(
                            "workshop_company_entities",
                        )
                    ]
                    if "ix_entity_name_trgm" not in ce_idx:
                        conn.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_entity_name_trgm "
                            "ON workshop_company_entities "
                            "USING GIN (canonical_name_normalized gin_trgm_ops)"
                        ))
                        conn.commit()
                        log.info(
                            "pg_trgm-Index ix_entity_name_trgm auf "
                            "workshop_company_entities(canonical_name_normalized) "
                            "angelegt.",
                        )
            except Exception as e:
                log.warning(
                    "Entity pg_trgm-Index konnte nicht angelegt werden: %s", e,
                )

            # Layer A: Embedding-Index (bge-m3, 1024 Dim) ueber alle Module.
            # Tabelle wird ueber Base.metadata.create_all angelegt. Hier nur
            # Extension + IVFFlat-Cosine-Index sicherstellen. Idempotent.
            # Kein automatischer Build im Lifespan — Initial-Build dauert
            # 30 min und wird ueber scripts/rebuild_embeddings.py getriggert.
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                if inspector.has_table("workshop_entity_embeddings"):
                    emb_idx = [
                        i["name"] for i in inspector.get_indexes(
                            "workshop_entity_embeddings",
                        )
                    ]
                    if "ix_entity_embedding_cosine" not in emb_idx:
                        conn.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_entity_embedding_cosine "
                            "ON workshop_entity_embeddings "
                            "USING ivfflat (embedding vector_cosine_ops) "
                            "WITH (lists = 100)"
                        ))
                        conn.commit()
                        log.info(
                            "IVFFlat-Cosine-Index ix_entity_embedding_cosine "
                            "auf workshop_entity_embeddings angelegt.",
                        )
            except Exception as e:
                log.warning(
                    "Entity-Embedding-Index konnte nicht angelegt werden: %s",
                    e,
                )

            # Phase 6b: Datengetriebene Beneficiary-Quellen-Configs.
            # Beim ersten Start seeden wir die Tabelle mit den Quellen, die
            # ueber `get_beneficiary_sources()` aus den Legacy-DataFrame-
            # Tabellen bekannt sind — pro Source ein leerer Eintrag mit
            # source_type='manual_upload', enabled=true, field_mapping=NULL.
            # Der Admin koennte sie spaeter per UI auf source_type=xlsx_url
            # umstellen und das Mapping pflegen.
            try:
                if inspector.has_table("workshop_beneficiary_sources_config"):
                    cfg_count = conn.execute(
                        text("SELECT COUNT(*) FROM workshop_beneficiary_sources_config")
                    ).scalar()
                    if cfg_count == 0:
                        # Lazy-Import vermeidet Zyklus zur dataframe_service.
                        from services.dataframe_service import get_beneficiary_sources
                        try:
                            seed_sources = get_beneficiary_sources()
                        except Exception:  # noqa: BLE001
                            log.warning(
                                "Beneficiary-Config-Seed: get_beneficiary_sources fehlgeschlagen — Tabelle bleibt leer."
                            )
                            seed_sources = []
                        seeded = 0
                        for src in seed_sources:
                            source_key = src.get("source") or ""
                            if not source_key:
                                continue
                            display_name = (
                                f"{src.get('bundesland') or 'unbekannt'} · "
                                f"{src.get('fonds') or 'EFRE'}"
                                + (f" · {src.get('periode')}" if src.get('periode') else "")
                            )
                            try:
                                conn.execute(text(
                                    "INSERT INTO workshop_beneficiary_sources_config "
                                    "(source_key, display_name, bundesland, fonds, periode, "
                                    " country_code, source_type, enabled, header_row, record_count) "
                                    "VALUES (:k, :n, :b, :f, :p, :cc, 'manual_upload', true, 0, :rc) "
                                    "ON CONFLICT (source_key) DO NOTHING"
                                ), {
                                    "k": source_key,
                                    "n": display_name[:200],
                                    "b": src.get("bundesland"),
                                    "f": src.get("fonds"),
                                    "p": src.get("periode"),
                                    "cc": src.get("country_code"),
                                    "rc": int(src.get("row_count") or 0),
                                })
                                seeded += 1
                            except Exception:  # noqa: BLE001
                                log.exception(
                                    "Beneficiary-Config-Seed fehlgeschlagen fuer %s",
                                    source_key,
                                )
                        if seeded:
                            conn.commit()
                            log.info(
                                "Beneficiary-Config: %d Default-Quellen geseeded.",
                                seeded,
                            )
            except Exception as e:
                log.warning("Beneficiary-Config-Seed-Migration fehlgeschlagen: %s", e)

            # State-Aid: Default-Quellen seeden (Plan §5.3)
            try:
                src_count = conn.execute(text("SELECT COUNT(*) FROM workshop_state_aid_sources")).scalar()
                if src_count == 0:
                    default_sources = [
                        ("tam_eu", "TAM — EU Public Search", "tam", None,
                         "https://webgate.ec.europa.eu/competition/transparency/public",
                         "Primaere Quelle. Awards aus allen EU-Mitgliedstaaten via TAM-Formular.", "yellow"),
                        ("tam_de", "TAM — Deutschland", "tam", "DEU",
                         "https://webgate.ec.europa.eu/competition/transparency/public",
                         "Phase-1-Slice: nur Awards mit Granting-Authority Deutschland.", "yellow"),
                        ("tam_at", "TAM — Oesterreich", "tam", "AUT",
                         "https://webgate.ec.europa.eu/competition/transparency/public",
                         "Phase-1-Slice: Awards mit Granting-Authority Oesterreich (alle 9 Bundeslaender).", "yellow"),
                        ("national_pl", "Polen — SUDOP", "national", "POL",
                         "https://sudop.uokik.gov.pl/home",
                         "Nationales Beihilfe-Register. Connector noch nicht implementiert.", "red"),
                        ("national_ro", "Rumaenien — REGAS", "national", "ROU",
                         "https://regas.consiliulconcurentei.ro/transparenta/index.html",
                         "Nationales Beihilfe-Register. Connector noch nicht implementiert.", "red"),
                        ("national_es", "Spanien — BDNS Trans", "national", "ESP",
                         "http://www.infosubvenciones.es/bdnstrans/GE/es/index",
                         "Nationales Beihilfe-Register. Connector noch nicht implementiert.", "red"),
                        ("national_si", "Slowenien — gov.si", "national", "SVN",
                         "https://www.gov.si/teme/objava-vecjih-prejemnikov-pomoci/",
                         "Nationales Beihilfe-Register. Connector noch nicht implementiert.", "red"),
                        ("cases_eu", "Competition Cases Search", "cases", None,
                         "https://competition-cases.ec.europa.eu/search",
                         "Verlinkte SA-Faelle der KOM. Wird nicht geharvested, nur per SA-Referenz verlinkt.", "green"),
                    ]
                    for sk, name, st, cc, url, note, qual in default_sources:
                        conn.execute(text(
                            "INSERT INTO workshop_state_aid_sources "
                            "(source_key, display_name, source_type, country_code, base_url, "
                            "coverage_note, quality, enabled, record_count) "
                            "VALUES (:k, :n, :st, :cc, :url, :note, :q, true, 0)"
                        ), {"k": sk, "n": name, "st": st, "cc": cc, "url": url, "note": note, "q": qual})
                    conn.commit()
                    log.info("State-Aid: %d Default-Quellen angelegt.", len(default_sources))
            except Exception as e:
                log.warning("State-Aid Source-Seed fehlgeschlagen: %s", e)

            # Initial-Admin: jan.riener@wirtschaft.hessen.de wird role=admin,
            # alle bestehenden mit Login werden status=active (= idempotent)
            conn.execute(text("""
                UPDATE workshop_registrations
                   SET role = 'admin', quota_bytes = 9223372036854775807
                 WHERE LOWER(email) = 'jan.riener@wirtschaft.hessen.de'
                   AND role <> 'admin'
            """))
            conn.commit()
            # bestehende Nutzer: status auf 'active' setzen wenn noch nicht
            conn.execute(text("""
                UPDATE workshop_registrations
                   SET approved_at = COALESCE(approved_at, created_at, now())
                 WHERE status = 'active' AND approved_at IS NULL
            """))
            conn.commit()
    except Exception as e:
        log.error("SQLAlchemy-Init fehlgeschlagen: %s", e)

    # pgvector-Tabelle initialisieren (knowledge_chunks)
    try:
        init_db()
        log.info("pgvector-Wissensdatenbank bereit.")
    except Exception as e:
        log.error("pgvector-Init fehlgeschlagen: %s", e)

    # Sanctions-Index in den Speicher laden (alle Quellen: eu_fsf, un_sc,
    # us_ofac_sdn, gb_hmt_sanctions, ch_seco). Fehlende CSV-Dateien werden
    # nicht synchron geladen — stattdessen triggert der Lifespan einen
    # Background-Refresh, der die fehlenden Quellen nachzieht.
    try:
        from services.sanctions_service import (
            warmup as sanctions_warmup,
            get_multi_service,
        )
        sanctions_warmup()

        svc = get_multi_service()
        missing = svc.missing_source_keys()
        if missing:
            log.info(
                "Sanctions: %d/%d Quelle(n) fehlen lokal (%s) — "
                "starte Background-Refresh …",
                len(missing), len(svc.sources), ",".join(missing),
            )

            async def _initial_refresh():
                """Holt fehlende Sanctions-CSVs im Hintergrund."""
                from services.scheduler import run_sanctions_refresh
                try:
                    # to_thread, weil refresh_from_source synchron blockt
                    import asyncio as _asyncio
                    await _asyncio.to_thread(run_sanctions_refresh, "lifespan")
                    log.info("Sanctions: Background-Refresh abgeschlossen.")
                except Exception:  # noqa: BLE001
                    log.exception("Sanctions: Background-Refresh fehlgeschlagen")

            import asyncio as _asyncio
            _asyncio.create_task(_initial_refresh())
    except Exception as e:  # noqa: BLE001
        log.warning("Sanctions-Warmup fehlgeschlagen: %s", e)

    # Ollama-Verbindung prüfen
    status = await check_ollama()
    if status["ok"]:
        log.info("Ollama erreichbar — Modelle: %s", status.get("models", []))
        await warmup_gateway_model()
    else:
        log.warning("Ollama nicht erreichbar: %s", status.get("error"))

    # Background-Scheduler für Auto-Harvest + Sanctions-Refresh (Plan v3.2 §16)
    import asyncio
    from services.scheduler import scheduler_loop
    scheduler_task = asyncio.create_task(scheduler_loop())

    yield
    # ── Shutdown ───────────────────────────────────────────
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    log.info("flowworkshop beendet.")


app = FastAPI(
    title="FlowWorkshop",
    description="KI-Workshop-Demo für EFRE-Prüfbehörden",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3004",
        "http://localhost:5173",
        "https://workshop.flowaudit.de",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Access-Logging fuer alle /api/*-Requests (DSGVO-konform: ip_hash, kein Body).
# Reihenfolge: nach CORS — sonst sehen wir bei Browser-Preflights 405-Antworten
# der Middleware-Kette und nicht das eigentliche Request-Ergebnis.
app.add_middleware(AccessLogMiddleware)

# Bestehende Router
app.include_router(workshop.router)
app.include_router(knowledge.router)
app.include_router(system.router)

# Neue CRUD + Assessment Router
app.include_router(projects.router)
app.include_router(checklists.router)
app.include_router(assessment.router)
app.include_router(demo_data.router)
app.include_router(dataframes.router)
app.include_router(beneficiaries.router)
app.include_router(reference_data.router)
app.include_router(event.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(sanctions.router)
app.include_router(forum.router)
app.include_router(automation.router)
app.include_router(docs_router.router)
app.include_router(notifications.router)
app.include_router(state_aid.router)
app.include_router(admin_access.router)
app.include_router(beneficiaries_sources.router)
# Phase 6d: Entity-Resolution (Master-Tabelle + Admin-Rebuild).
app.include_router(entities_router.router)
app.include_router(entities_router.admin_router)
# Layer A: Embedding-Index (bge-m3) ueber alle Module — semantische Suche.
app.include_router(embeddings_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "flowworkshop"}
