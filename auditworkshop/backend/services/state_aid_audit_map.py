"""flowworkshop · services/state_aid_audit_map.py

Erzeugt eine PNG-Karte für den Cross-Register-Prüfbericht:
- OSM-Tiles als Hintergrund (tile.openstreetmap.org)
- NUTS-Layer als Outline (lokale GeoJSONs in /app/data/geo)
- Marker je NUTS-Region, in der das gesuchte Unternehmen Treffer hat
  (Marker-Größe ∝ Award-Anzahl, Zahl im Marker = Trefferzahl)

Bewusst ohne geopandas/matplotlib/contextily — nutzt nur Pillow + httpx,
um Container-Image schlank zu halten. Web-Mercator-Math + GeoJSON-Parsing
in <250 Zeilen.

DSGVO-Hinweis: Tile-Fetch geht an externes OSM-Tile-Netz. Der Cover-Block
des Berichts erwähnt das explizit.
"""
from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

# ── Konstanten ───────────────────────────────────────────────────────────────

OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# OSM Tile Usage Policy verlangt einen identifizierenden User-Agent.
OSM_USER_AGENT = "FlowWorkshop-AuditReport/1.0 (jan.riener@vwvg.de)"
TILE_SIZE = 256
GEO_DIR = Path("/app/data/geo")

# Process-lokaler Tile-Cache (lebt nur für die Bericht-Erzeugung). Reicht,
# weil eine Karte typischerweise 6–20 Tiles braucht und der Bericht in
# einem Request abgewickelt wird.
_tile_cache: dict[tuple[int, int, int], Image.Image] = {}


# ── Web-Mercator ─────────────────────────────────────────────────────────────


def latlon_to_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web-Mercator: Welt-Koordinate → Pixel bei gegebenem Zoom."""
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(max(-85.0, min(85.0, lat)))
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


# ── GeoJSON-Helper ───────────────────────────────────────────────────────────


def _polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Mittelpunkt eines GeoJSON-Polygon-Rings. Liefert (lat, lon).

    Bewusst einfach (arithmetisches Mittel der Stützpunkte) — reicht für
    Marker-Platzierung, kein echtes Flächen-Centroid nötig.
    """
    if not ring:
        return 0.0, 0.0
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _load_nuts_layer(country_code: str, level: int) -> dict[str, dict[str, Any]]:
    """Lädt NUTS-GeoJSON für ein Land/Level und liefert eine Map
    NUTS_ID → {"centroid": (lat,lon), "polygons": [[(lon,lat), ...], ...]}.

    Liefert {}, wenn die GeoJSON-Datei nicht existiert (z.B. unbekanntes Land).
    """
    f = GEO_DIR / f"nuts{level}_{country_code.lower()}.geojson"
    if not f.exists():
        log.warning("NUTS-GeoJSON nicht gefunden: %s", f)
        return {}
    try:
        with f.open(encoding="utf-8") as fp:
            gj = json.load(fp)
    except Exception:  # noqa: BLE001
        log.exception("NUTS-GeoJSON nicht parsbar: %s", f)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for feat in gj.get("features") or []:
        props = feat.get("properties") or {}
        nid = props.get("NUTS_ID")
        if not nid:
            continue
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        polys: list[list[tuple[float, float]]] = []
        if gtype == "Polygon":
            ring = geom["coordinates"][0]
            polys.append([(p[0], p[1]) for p in ring])
        elif gtype == "MultiPolygon":
            for sub in geom["coordinates"]:
                polys.append([(p[0], p[1]) for p in sub[0]])
        else:
            continue
        # Centroid aus größtem Polygon
        biggest = max(polys, key=len) if polys else []
        centroid = _polygon_centroid([[lon, lat] for lon, lat in biggest])
        out[nid] = {
            "name": props.get("NAME_LATN") or props.get("NUTS_NAME") or nid,
            "centroid": centroid,
            "polygons": polys,
        }
    return out


# ── OSM-Tiles ────────────────────────────────────────────────────────────────


def _fetch_tile(z: int, x: int, y: int, *, client: httpx.Client) -> Image.Image | None:
    """Holt einen OSM-Tile. Liefert None bei Fehler — der Aufrufer entscheidet,
    ob die Karte trotzdem gerendert wird (z.B. mit Lücken)."""
    n = 1 << z
    # Tile-Koordinaten wrappen/clamp'en
    if y < 0 or y >= n:
        return None
    x = x % n
    key = (z, x, y)
    if key in _tile_cache:
        return _tile_cache[key]
    url = OSM_TILE_URL.format(z=z, x=x, y=y)
    try:
        r = client.get(url)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        _tile_cache[key] = img
        return img
    except Exception as exc:  # noqa: BLE001
        log.warning("OSM-Tile %d/%d/%d fehlgeschlagen: %s", z, x, y, exc)
        return None


# ── Hauptfunktion ────────────────────────────────────────────────────────────


def render_audit_map(
    awards: list[dict],
    *,
    query_name: str,
    country_codes: list[str] | None = None,
    width: int = 900,
    height: int = 760,
    nuts_level: int = 1,
    issued_at: str | None = None,
) -> bytes | None:
    """Rendert die Karte als PNG-Bytes.

    awards: state-aid awards (List[dict]) — relevante Felder: nuts_code,
            country_code, aid_amount_eur.
    query_name: Name der gesuchten Firma (für Titel + Legende).
    country_codes: ['DE'], ['AT'] oder ['DE','AT']. Default leitet aus den
                   Awards ab.
    nuts_level: 1 (Bundesland) reicht für eine A4-Seiten-Übersicht;
                3 (Kreis) wäre zu kleinteilig in dem Format.

    Liefert None, wenn keine Awards mit NUTS-Code vorhanden oder das
    OSM-Tile-Netz nicht erreichbar ist.
    """
    if not awards:
        return None

    # ── Layout-Reservierung für Titel + Karten-Frame + Quellzeile ───────────
    title_h = 42           # Oberer Streifen: Titel
    source_h = 38          # Unterer Streifen: Quelle/Beschriftung
    frame_margin = 18      # Rand um die Karte (links/rechts/oben/unten)
    map_x0 = frame_margin
    map_y0 = title_h + frame_margin
    map_x1 = width - frame_margin
    map_y1 = height - source_h - frame_margin
    map_w = map_x1 - map_x0
    map_h = map_y1 - map_y0

    # Länder-Set aus den Awards bestimmen (Fallback: nuts_code-Prefix).
    if country_codes is None:
        ccs: set[str] = set()
        for a in awards:
            cc = (a.get("country_code") or "").upper().strip()
            if not cc:
                # aus NUTS-Code ableiten (erste 2 Buchstaben)
                nc = (a.get("nuts_code") or "").upper().strip()
                if len(nc) >= 2:
                    cc = nc[:2]
            if cc in {"DE", "AT"}:
                ccs.add(cc)
        country_codes = sorted(ccs) or ["DE"]

    # NUTS-Layer aller relevanten Länder laden + mergen
    nuts_layer: dict[str, dict[str, Any]] = {}
    for cc in country_codes:
        nuts_layer.update(_load_nuts_layer(cc, nuts_level))
    if not nuts_layer:
        log.warning("Keine NUTS-Layer ladbar für %s", country_codes)
        return None

    # Awards je NUTS-Region (auf gewünschtes Level kürzen) aggregieren
    target_len = 2 + nuts_level  # DE1, DEA, AT1, AT2, ...
    hits: dict[str, dict[str, float]] = {}
    for a in awards:
        nc = (a.get("nuts_code") or "").upper().strip()
        if len(nc) < target_len:
            continue
        nkey = nc[:target_len]
        if nkey not in nuts_layer:
            continue
        amount = float(a.get("aid_amount_eur") or 0.0)
        if nkey not in hits:
            hits[nkey] = {"count": 0, "sum": 0.0}
        hits[nkey]["count"] += 1
        hits[nkey]["sum"] += amount

    if not hits:
        log.info("Keine Awards mit NUTS-Code für Karte verfügbar")
        return None

    # BBox aller getroffenen Regionen
    centroids = [nuts_layer[k]["centroid"] for k in hits]
    lats = [c[0] for c in centroids]
    lons = [c[1] for c in centroids]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    # Padding (mindestens 0.5°, damit Marker nicht am Rand kleben)
    lat_pad = max((lat_max - lat_min) * 0.18, 0.6)
    lon_pad = max((lon_max - lon_min) * 0.18, 0.8)
    lat_min -= lat_pad
    lat_max += lat_pad
    lon_min -= lon_pad
    lon_max += lon_pad

    # Zoom-Level wählen, dass BBox in (map_w, map_h) passt
    chosen_zoom = 5
    for z in range(10, 3, -1):
        x1, _ = latlon_to_pixel(lat_max, lon_min, z)
        x2, _ = latlon_to_pixel(lat_min, lon_max, z)
        _, y1 = latlon_to_pixel(lat_max, lon_min, z)
        _, y2 = latlon_to_pixel(lat_min, lon_max, z)
        if abs(x2 - x1) <= map_w - 20 and abs(y2 - y1) <= map_h - 20:
            chosen_zoom = z
            break

    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2
    cx, cy = latlon_to_pixel(center_lat, center_lon, chosen_zoom)
    # x0_px/y0_px sind die "Welt-Pixel"-Koordinaten der linken oberen Ecke
    # des inneren Karten-Bereichs (nicht der ganzen Leinwand).
    x0_px = cx - map_w / 2
    y0_px = cy - map_h / 2

    # Volle Leinwand (Hintergrund hellgrau für Frame-Bereich)
    canvas = Image.new("RGBA", (width, height), (250, 250, 250, 255))
    # Karten-Bereich als sub-Image rendern, später auf Leinwand pasten
    map_canvas = Image.new("RGBA", (map_w, map_h), (235, 235, 235, 255))

    x_tile_start = int(math.floor(x0_px / TILE_SIZE))
    x_tile_end = int(math.ceil((x0_px + map_w) / TILE_SIZE))
    y_tile_start = int(math.floor(y0_px / TILE_SIZE))
    y_tile_end = int(math.ceil((y0_px + map_h) / TILE_SIZE))

    total_tiles = max(1, (x_tile_end - x_tile_start) * (y_tile_end - y_tile_start))
    failed = 0
    with httpx.Client(
        timeout=httpx.Timeout(8.0, connect=4.0),
        headers={"User-Agent": OSM_USER_AGENT},
        follow_redirects=True,
    ) as client:
        for tx in range(x_tile_start, x_tile_end):
            for ty in range(y_tile_start, y_tile_end):
                tile = _fetch_tile(chosen_zoom, tx, ty, client=client)
                if tile is None:
                    failed += 1
                    continue
                paste_x = int(tx * TILE_SIZE - x0_px)
                paste_y = int(ty * TILE_SIZE - y0_px)
                map_canvas.paste(tile, (paste_x, paste_y), tile)

    if failed >= total_tiles:
        log.warning("Alle OSM-Tiles fehlgeschlagen — keine Karte")
        return None

    # ── Schriftarten ────────────────────────────────────────────────────────
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    except Exception:  # noqa: BLE001
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # ── NUTS-Layer auf map_canvas ───────────────────────────────────────────
    # Transparente Füllung auf Overlay; harte Outlines direkt auf map_canvas.
    map_draw = ImageDraw.Draw(map_canvas, "RGBA")
    fill_overlay = Image.new("RGBA", map_canvas.size, (0, 0, 0, 0))
    fill_draw = ImageDraw.Draw(fill_overlay)

    for nid, info in nuts_layer.items():
        is_hit = nid in hits
        for ring in info["polygons"]:
            screen = [
                (px - x0_px, py - y0_px)
                for lon, lat in ring
                for px, py in [latlon_to_pixel(lat, lon, chosen_zoom)]
            ]
            if len(screen) < 3:
                continue
            if is_hit:
                fill_draw.polygon(screen, fill=(220, 38, 38, 60))
                map_draw.line(screen + [screen[0]], fill=(180, 28, 28, 230), width=2)
            else:
                map_draw.line(screen + [screen[0]], fill=(90, 90, 90, 140), width=1)

    map_canvas = Image.alpha_composite(map_canvas, fill_overlay)
    map_draw = ImageDraw.Draw(map_canvas, "RGBA")

    # ── Marker je Treffer-Region ────────────────────────────────────────────
    max_count = max(h["count"] for h in hits.values())
    for nid, info in hits.items():
        lat, lon = nuts_layer[nid]["centroid"]
        px, py = latlon_to_pixel(lat, lon, chosen_zoom)
        sx, sy = px - x0_px, py - y0_px
        ratio = info["count"] / max_count
        radius = int(10 + ratio * 18)
        map_draw.ellipse(
            (sx - radius, sy - radius, sx + radius, sy + radius),
            fill=(220, 38, 38, 230), outline=(120, 0, 0, 255), width=2,
        )
        count_text = str(int(info["count"]))
        try:
            tw = font_label.getlength(count_text)
        except Exception:  # noqa: BLE001
            tw = 8 * len(count_text)
        map_draw.text((sx - tw / 2, sy - 7), count_text,
                      fill=(255, 255, 255, 255), font=font_label)

    # ── Nordpfeil oben rechts der Karte ─────────────────────────────────────
    arrow_size = 38
    ax = map_w - arrow_size - 14
    ay = 14
    # Hintergrund-Kreis (halbtransparent weiß)
    map_draw.ellipse(
        (ax, ay, ax + arrow_size, ay + arrow_size),
        fill=(255, 255, 255, 220), outline=(60, 60, 60, 255), width=1,
    )
    # Pfeil-Polygon (Spitze nach oben, gefüllt)
    cx_a = ax + arrow_size / 2
    cy_a = ay + arrow_size / 2
    map_draw.polygon([
        (cx_a, cy_a - 13),
        (cx_a - 7, cy_a + 9),
        (cx_a, cy_a + 4),
        (cx_a + 7, cy_a + 9),
    ], fill=(30, 30, 30, 255))
    # N-Label
    try:
        nw = font_label.getlength("N")
    except Exception:  # noqa: BLE001
        nw = 7
    map_draw.text(
        (cx_a - nw / 2, cy_a + 8),
        "N", fill=(30, 30, 30, 255), font=font_label,
    )

    # ── Legende unten links der Karte ───────────────────────────────────────
    leg_w, leg_h = 248, 72
    leg_x, leg_y = 12, map_h - leg_h - 12
    legend = Image.new("RGBA", (leg_w, leg_h), (255, 255, 255, 235))
    ldraw = ImageDraw.Draw(legend)
    ldraw.rectangle((0, 0, leg_w - 1, leg_h - 1),
                    outline=(70, 70, 70, 255), width=1)
    ldraw.text((10, 6), "Legende", fill=(20, 20, 20, 255), font=font_label)
    # Marker-Symbol
    ldraw.ellipse((14, 28, 30, 44), fill=(220, 38, 38, 220),
                  outline=(120, 0, 0, 255), width=2)
    ldraw.text((38, 30), "Award-Anzahl je NUTS-Region (Zahl im Marker)",
               fill=(40, 40, 40, 255), font=font_small)
    # Flächen-Symbol
    ldraw.rectangle((14, 50, 30, 62), fill=(220, 70, 50, 110),
                    outline=(180, 28, 28, 230), width=2)
    ldraw.text((38, 52), "Bundesland mit Treffer(n) (rot überlagert)",
               fill=(40, 40, 40, 255), font=font_small)
    map_canvas.paste(legend, (leg_x, leg_y), legend)

    # ── map_canvas auf die Hauptleinwand pasten ────────────────────────────
    canvas.paste(map_canvas, (map_x0, map_y0), map_canvas)

    # ── Rahmen um die Karte (zweifach: außen dünn, innen kräftig) ───────────
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle(
        (map_x0 - 1, map_y0 - 1, map_x1, map_y1),
        outline=(40, 40, 40, 255), width=2,
    )

    # ── Titel oben (Beschriftung) ───────────────────────────────────────────
    title = f"Räumliche Verteilung der State-Aid-Awards · {query_name}"
    try:
        tw = font_title.getlength(title)
    except Exception:  # noqa: BLE001
        tw = 9 * len(title)
    # Titel zentriert, falls zu breit linksbündig mit Padding
    if tw <= width - 40:
        tx = (width - tw) // 2
    else:
        tx = 20
        # Kürzen falls extrem lang
        max_chars = int((width - 40) / 9)
        if len(title) > max_chars:
            title = title[: max_chars - 1] + "…"
    draw.text((tx, 14), title, fill=(20, 20, 20, 255), font=font_title)

    # ── Quellzeile unten (Datenstand + Attribution) ─────────────────────────
    src_y = height - source_h + 8
    line1 = "Hintergrund: © OpenStreetMap Mitwirkende (tile.openstreetmap.org)  ·  NUTS-1-Geometrien: Eurostat (lokaler Vektor-Datensatz)"
    if issued_at:
        line2 = f"Datenstand: {issued_at}  ·  Marker = State-Aid-Awards je NUTS-Region (Stand siehe Cover)"
    else:
        line2 = "Marker = Anzahl State-Aid-Awards je NUTS-Region (Stand siehe Cover)"
    # Beide Zeilen zentriert
    for i, ln in enumerate((line1, line2)):
        try:
            lw = font_small.getlength(ln)
        except Exception:  # noqa: BLE001
            lw = 6 * len(ln)
        lx = max(20, (width - lw) // 2)
        draw.text((lx, src_y + i * 13), ln, fill=(60, 60, 60, 255), font=font_small)

    # ── Trennlinie über Quellzeile ──────────────────────────────────────────
    draw.line(
        (frame_margin, height - source_h - 2,
         width - frame_margin, height - source_h - 2),
        fill=(180, 180, 180, 255), width=1,
    )

    out_buf = io.BytesIO()
    canvas.convert("RGB").save(out_buf, format="PNG", optimize=True)
    return out_buf.getvalue()
