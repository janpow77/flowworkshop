"""
flowworkshop · routers/documents.py
Demo-Dokumente für Workshop-Szenarien.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Demo-Dokumente lazy laden
_DEMOS = {}

def _load_demos():
    if _DEMOS:
        return
    from data.demo_documents import foerderbescheid, prueffeststellungen, eu_verordnung
    from data.demo_documents import ai_act_einordnung, benchmark_roi
    from data.demo_documents import foerderbescheid_esf, prueffeststellungen_esf
    _DEMOS["foerderbescheid"] = {"title": foerderbescheid.TITLE, "content": foerderbescheid.CONTENT}
    _DEMOS["prueffeststellungen"] = {"title": prueffeststellungen.TITLE, "content": prueffeststellungen.CONTENT}
    _DEMOS["eu_verordnung"] = {"title": eu_verordnung.TITLE, "content": eu_verordnung.CONTENT}
    _DEMOS["ai_act_einordnung"] = {"title": ai_act_einordnung.TITLE, "content": ai_act_einordnung.CONTENT}
    _DEMOS["benchmark_roi"] = {"title": benchmark_roi.TITLE, "content": benchmark_roi.CONTENT}
    _DEMOS["foerderbescheid_esf"] = {"title": foerderbescheid_esf.TITLE, "content": foerderbescheid_esf.CONTENT}
    _DEMOS["prueffeststellungen_esf"] = {"title": prueffeststellungen_esf.TITLE, "content": prueffeststellungen_esf.CONTENT}

@router.get("/demo")
def list_demos():
    _load_demos()
    return [{"name": k, "title": v["title"]} for k, v in _DEMOS.items()]

@router.get("/demo/{name}")
def get_demo(name: str):
    _load_demos()
    doc = _DEMOS.get(name)
    if not doc:
        raise HTTPException(404, f"Demo-Dokument '{name}' nicht gefunden.")
    return doc
