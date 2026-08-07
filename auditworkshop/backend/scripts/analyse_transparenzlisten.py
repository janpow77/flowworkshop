#!/usr/bin/env python3
"""Analysiert die Transparenzlisten der Länder: Blätter, Kopfzeile, Spalten.

Laedt jede erreichbare Quelle, bestimmt das Tabellenblatt und die Zeile mit
den Spaltenueberschriften und zeigt die erkannten Spaltennamen. Grundlage
fuer field_mapping/header_row je Quelle.
"""
import io
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.beneficiary_sources_config import BeneficiarySourceConfig  # noqa: E402

REG = json.loads(
    Path("/app/data/transparenzlisten_urls.json").read_text(encoding="utf-8")
)["sources"]

ZIEL = sys.argv[1:] if len(sys.argv) > 1 else None

HEADERS = {"User-Agent": "Auditworkshop-EFRE-Demo/1.0 (Workshop)"}


def norm(s):
    s = (s or "").lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    return s.replace("ue", "u").replace("oe", "o").replace("ae", "a").replace("-", "").replace(" ", "")


def split_key(k):
    parts = k.split("_")
    for i, p in enumerate(parts):
        if p in ("efre", "esf", "jtf", "amif", "isf"):
            return norm("_".join(parts[:i])), p
    return norm(k), ""


by_lf = {}
for e in REG:
    by_lf.setdefault((norm(e.get("bundesland")), (e.get("fonds") or "").lower()), e)

db = SessionLocal()
keys = [c.source_key for c in db.query(BeneficiarySourceConfig).order_by(
    BeneficiarySourceConfig.source_key)]
db.close()

for key in keys:
    if ZIEL and key not in ZIEL:
        continue
    entry = by_lf.get(split_key(key))
    if not entry or not entry.get("url") or entry.get("status") != "ok":
        continue
    url = entry["url"]
    print(f"\n{'='*78}\n{key}")
    try:
        with httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS) as c:
            content = c.get(url).content
    except Exception as exc:
        print(f"  Download-Fehler: {exc}")
        continue

    if content[:4] != b"PK\x03\x04":
        print(f"  Kein XLSX (erste Bytes {content[:8]!r}) — vermutlich CSV")
        try:
            txt = content.decode("utf-8", "replace")[:400]
            print("  Erste Zeilen:", txt.splitlines()[:3])
        except Exception:
            pass
        continue

    try:
        xl = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        print(f"  Excel-Fehler: {exc}")
        continue

    print(f"  Blätter: {xl.sheet_names}")
    blatt = xl.sheet_names[0]
    roh = pd.read_excel(xl, sheet_name=blatt, header=None, nrows=12)
    # Kopfzeile = erste Zeile mit >= 3 nicht-leeren Textzellen
    kopf = None
    for i in range(len(roh)):
        zeile = roh.iloc[i]
        texte = [str(v).strip() for v in zeile if isinstance(v, str) and str(v).strip()]
        if len(texte) >= 3:
            kopf = i
            break
    print(f"  Erkannte Kopfzeile: {kopf}")
    if kopf is not None:
        spalten = [str(v).strip() for v in roh.iloc[kopf] if str(v) != "nan"]
        print(f"  Spalten ({len(spalten)}):")
        for s in spalten[:14]:
            print(f"     - {s[:70]}")
