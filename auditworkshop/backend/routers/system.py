"""
flowworkshop · routers/system.py
GPU- und System-Metriken (kompatibel mit PipelineWidget).
"""
import json
import subprocess
import urllib.request

from fastapi import APIRouter
import psutil

from config import (
    ALLOW_REMOTE_GEOCODING,
    ALLOW_REMOTE_TILES,
    EGPU_GATEWAY_APP_ID,
    EGPU_GATEWAY_URL,
    LLM_BACKEND,
    MODEL_NAME,
    OLLAMA_URL,
)
from services.ollama_service import check_ollama

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/gpu")
def get_gpu():
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,utilization.gpu,power.draw,"
             "temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        gpus = []
        for line in r.stdout.strip().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) < 7:
                continue
            gpus.append({
                "index": int(p[0]), "name": p[1],
                "utilization": float(p[2]), "power_draw": float(p[3]),
                "temperature": int(p[4]),
                "mem_used": int(p[5]), "mem_total": int(p[6]),
            })
        return {"ok": True, "gpus": gpus}
    except Exception as e:
        return {"ok": False, "error": str(e), "gpus": []}


def _get_ollama_models() -> list[dict]:
    """Fragt Ollama /api/ps ab und liefert aktuell geladene Modelle."""
    if LLM_BACKEND in {"egpu-manager", "egpu_manager", "gateway"}:
        try:
            url = f"{EGPU_GATEWAY_URL}/api/llm/providers"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())

            models = []
            seen = set()
            for provider in data.get("providers", []):
                if not provider.get("healthy"):
                    continue
                for name in provider.get("models", []):
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    models.append({
                        "name": name,
                        "size_gb": 0,
                        "vram_gb": 0,
                        "expires_at": "",
                        "provider": provider.get("name", "unknown"),
                    })

            if MODEL_NAME and MODEL_NAME not in seen:
                models.insert(0, {
                    "name": MODEL_NAME,
                    "size_gb": 0,
                    "vram_gb": 0,
                    "expires_at": "",
                    "provider": EGPU_GATEWAY_APP_ID,
                })
            return models
        except Exception:
            return []

    try:
        url = f"{OLLAMA_URL}/api/ps"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        models = []
        for m in data.get("models", []):
            name = m.get("model", m.get("name", "unknown"))
            size_gb = round(m.get("size", 0) / 1024**3, 1) if m.get("size") else 0
            vram_gb = round(m.get("size_vram", 0) / 1024**3, 1) if m.get("size_vram") else 0
            models.append({
                "name": name,
                "size_gb": size_gb,
                "vram_gb": vram_gb,
                "expires_at": m.get("expires_at", ""),
            })
        return models
    except Exception:
        return []


def _get_container_ram() -> dict:
    """Liest cgroup-Limits (Docker). Fällt auf Host-RAM zurück."""
    result = {"used_gb": 0.0, "limit_gb": 0.0, "host": False}
    for mem_file, limit_file in [
        ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
        ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ]:
        try:
            with open(mem_file) as f:
                used = int(f.read().strip())
            with open(limit_file) as f:
                raw = f.read().strip()
            limit = int(raw) if raw not in ("max", "9223372036854771712") else 0
            if limit > 0 and limit < 2**62:
                result["used_gb"] = round(used / 1024**3, 1)
                result["limit_gb"] = round(limit / 1024**3, 1)
                return result
        except Exception:
            pass
    vm = psutil.virtual_memory()
    result["used_gb"] = round(vm.used / 1024**3, 1)
    result["limit_gb"] = round(vm.total / 1024**3, 1)
    result["host"] = True
    return result


@router.get("/info")
def get_info():
    """System-Stats im PipelineWidget-kompatiblen Format."""
    vm = psutil.virtual_memory()
    workers = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmd = " ".join(proc.info["cmdline"] or []).lower()
            if "ollama" in name or "ollama" in cmd:
                rss = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
                workers.append({"pid": proc.info["pid"], "rss_gb": round(rss / 1024**3, 2)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    net = psutil.net_io_counters()
    models = _get_ollama_models()
    cram = _get_container_ram()

    return {
        "ok": True,
        "cpu": {
            "percent": round(psutil.cpu_percent(interval=0.3), 1),
            "cores": psutil.cpu_count(logical=True),
        },
        "host_ram": {
            "used_gb": round(vm.used / 1024**3, 1),
            "total_gb": round(vm.total / 1024**3, 1),
            "free_gb": round(vm.available / 1024**3, 1),
        },
        "container_ram": cram,
        "ollama": {
            "worker_count": len(workers),
            "workers": workers,
            "total_rss_gb": round(sum(w["rss_gb"] for w in workers), 2),
            "models": models,
        },
        "network": {
            "recv_mb": round(net.bytes_recv / 1024**2, 1),
            "sent_mb": round(net.bytes_sent / 1024**2, 1),
        },
    }


@router.get("/ollama")
async def get_ollama_status():
    return await check_ollama()


@router.get("/profile")
def get_profile():
    return {
        "model_name": MODEL_NAME,
        "llm_backend": LLM_BACKEND,
        "llm_endpoint": EGPU_GATEWAY_URL if LLM_BACKEND in {"egpu-manager", "egpu_manager", "gateway"} else OLLAMA_URL,
        "privacy_mode": not (ALLOW_REMOTE_GEOCODING or ALLOW_REMOTE_TILES),
        "allow_remote_geocoding": ALLOW_REMOTE_GEOCODING,
        "allow_remote_tiles": ALLOW_REMOTE_TILES,
    }
