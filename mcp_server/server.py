"""
server.py — ClinAI MCP Server (port 8001)

Architecture : FastAPI pur — pas de dépendance à la lib `mcp`.
Les agents l'invoquent via POST /call (JSON-RPC simplifié).
LangGraph Studio peut inspecter la liste des outils via GET /tools.

Endpoints :
  POST /call                → invocation d'un outil par les agents
  GET  /tools               → liste des outils (pour Studio / debug)
  GET  /logs                → historique des consultations loggées
  GET  /health              → santé du serveur

Lancement :
  cd mcp_server && python server.py
  → http://localhost:8001
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("clinai.mcp")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "consultations.log"

# ── Données médicales éducatives ─────────────────────────────────────────

SYMPTOM_DB: dict[str, str] = {
    "toux":               "Réflexe de défense respiratoire. Causes : infection virale, asthme, allergie. Durée > 3 sem → consultation.",
    "fièvre":             "Température > 38 °C — réponse immunitaire. > 39,5 °C ou > 3 j → consultation.",
    "douleur thoracique": "Origines variées. Oppressante + irradiation bras gauche → URGENCE cardiovasculaire immédiate.",
    "céphalée":           "Tension, migraine, déshydratation, tension oculaire. Céphalée brutale sévère → URGENCE.",
    "dyspnée":            "Essoufflement. Causes : effort, anxiété, asthme, IC. Dyspnée au repos → consultation urgente.",
    "vomissement":        "Si répétés : risque déshydratation. Avec fièvre élevée ou sang → consultation.",
    "diarrhée":           "Selles liquides > 3/j. Surveiller hydratation. > 48 h ou fièvre → consultation.",
    "fatigue":            "Asthénie fréquente. Causes : infection, anémie, surmenage. Persistante > 2 sem → bilan.",
    "symptôme non spécifié": "Symptôme non répertorié — évaluation clinique recommandée.",
}

ICD_MAP: dict[str, tuple[str, str]] = {
    "respiratoire":        ("J00-J99",  "Maladies de l'appareil respiratoire"),
    "cardiaque":           ("I00-I99",  "Maladies de l'appareil circulatoire"),
    "digestif":            ("K00-K93",  "Maladies de l'appareil digestif"),
    "neurologique":        ("G00-G99",  "Maladies du système nerveux"),
    "musculosquelettique": ("M00-M99",  "Système ostéo-articulaire"),
    "infectieux":          ("A00-B99",  "Maladies infectieuses et parasitaires"),
    "mental":              ("F00-F99",  "Troubles mentaux et du comportement"),
    "dermatologique":      ("L00-L99",  "Maladies de la peau"),
    "endocrinien":         ("E00-E90",  "Maladies endocriniennes et métaboliques"),
    "général":             ("Z00-Z99",  "Facteurs influant sur l'état de santé"),
}

RED_FLAGS: list[str] = [
    "douleur thoracique oppressante",
    "dyspnée au repos",
    "perte de conscience",
    "paralysie soudaine",
    "céphalée brutale sévère",
    "hémoptysie (sang dans les crachats)",
    "sang dans les selles",
    "confusion mentale aiguë",
    "fièvre > 40 °C",
    "convulsions",
    "douleur abdominale sévère",
    "sueurs froides avec douleur thoracique",
    "irradiation vers le bras gauche",
    "vision double ou trouble brutal",
    "difficulté à parler soudaine",
]


# ── Implémentation des outils ─────────────────────────────────────────────

def _lookup_symptom_info(symptom: str) -> str:
    t = (symptom or "").lower().strip()
    for key, info in SYMPTOM_DB.items():
        if key in t or t in key:
            return f"[INFO ÉDUCATIVE — non diagnostique]\n{info}"
    return f"Symptôme '{symptom}' non répertorié. Consultez un professionnel de santé."


def _get_icd_suggestion(clinical_domain: str) -> str:
    t = (clinical_domain or "").lower().strip()
    for key, (code, title) in ICD_MAP.items():
        if key in t or t in key:
            return f"CIM-10 : {code} — {title}  (éducatif uniquement)"
    return "Domaine non reconnu. Référez-vous à la classification CIM-10 complète."


def _get_red_flag_keywords() -> list[str]:
    return RED_FLAGS


def _log_consultation(
    session_id: str,
    patient_name: str,
    severity: str,
    summary: str,
) -> str:
    entry = {
        "ts":           datetime.now().isoformat(),
        "session_id":   session_id,
        "patient_name": patient_name,
        "severity":     severity,
        "summary":      (summary or "")[:500],
    }
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info(f"[MCP:log_consultation] session={session_id} severity={severity}")
    return f"✅ Consultation '{session_id}' enregistrée dans {LOG_FILE.name}."


# Registre : nom_outil → callable(arguments_dict) → Any
TOOLS: dict[str, Any] = {
    "lookup_symptom_info":   lambda a: _lookup_symptom_info(a.get("symptom", "")),
    "get_icd_suggestion":    lambda a: _get_icd_suggestion(a.get("clinical_domain", "")),
    "get_red_flag_keywords": lambda a: _get_red_flag_keywords(),
    "log_consultation":      lambda a: _log_consultation(
        a.get("session_id", ""),
        a.get("patient_name", ""),
        a.get("severity", ""),
        a.get("summary", ""),
    ),
}

TOOL_SCHEMAS = [
    {
        "name": "lookup_symptom_info",
        "description": "Retourne des informations éducatives (non diagnostiques) sur un symptôme.",
        "inputSchema": {
            "type": "object",
            "properties": {"symptom": {"type": "string", "description": "Nom du symptôme en français"}},
            "required": ["symptom"],
        },
    },
    {
        "name": "get_icd_suggestion",
        "description": "Retourne une suggestion de chapitre CIM-10 pour un domaine clinique (éducatif).",
        "inputSchema": {
            "type": "object",
            "properties": {"clinical_domain": {"type": "string", "description": "Domaine clinique (respiratoire, cardiaque…)"}},
            "required": ["clinical_domain"],
        },
    },
    {
        "name": "get_red_flag_keywords",
        "description": "Retourne la liste des mots-clés de signaux d'alarme cliniques (red flags).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "log_consultation",
        "description": "Persiste un résumé de consultation dans le fichier de log local.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "string"},
                "patient_name": {"type": "string"},
                "severity":     {"type": "string", "enum": ["Bénin", "Modéré", "Urgent"]},
                "summary":      {"type": "string"},
            },
            "required": ["session_id", "patient_name", "severity", "summary"],
        },
    },
]


# ── FastAPI app ───────────────────────────────────────────────────────────

app = FastAPI(
    title="ClinAI MCP Server",
    description="Model Context Protocol server — outils cliniques pour les agents LangGraph.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CallRequest(BaseModel):
    name: str
    arguments: dict = {}


@app.post("/call", summary="Invoquer un outil MCP")
async def call_tool(req: CallRequest):
    """
    Point d'entrée principal utilisé par les agents LangGraph.
    Retourne le résultat au format MCP content.
    """
    logger.info(f"[/call] tool={req.name!r}  args={req.arguments}")

    if req.name not in TOOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Outil '{req.name}' introuvable. Disponibles : {list(TOOLS)}",
        )

    try:
        result = TOOLS[req.name](req.arguments)
        # Sérialiser les listes/dicts en JSON string pour le format content
        if isinstance(result, (list, dict)):
            text = json.dumps(result, ensure_ascii=False)
        else:
            text = str(result)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    except Exception as exc:
        logger.error(f"[/call] Erreur dans '{req.name}': {exc}")
        return {"content": [{"type": "text", "text": f"Erreur : {exc}"}], "isError": True}


@app.get("/tools", summary="Lister les outils disponibles")
async def list_tools():
    """Retourne le schéma de tous les outils (compatible MCP / LangGraph Studio)."""
    return {"tools": TOOL_SCHEMAS}


@app.get("/logs", summary="Historique des consultations")
async def get_logs():
    """Retourne toutes les consultations loggées."""
    if not LOG_FILE.exists():
        return {"count": 0, "logs": []}
    logs = []
    with open(LOG_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return {"count": len(logs), "logs": logs}


@app.get("/health", summary="Santé du serveur MCP")
async def health():
    return {
        "status": "ok",
        "service": "ClinAI MCP Server",
        "version": "1.0.0",
        "tools_count": len(TOOLS),
        "tools": list(TOOLS.keys()),
        "log_file": str(LOG_FILE),
        "log_entries": sum(1 for _ in open(LOG_FILE, encoding="utf-8")) if LOG_FILE.exists() else 0,
    }


if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  ClinAI MCP Server — http://localhost:8001")
    logger.info("  POST /call   → invocation outil (agents)")
    logger.info("  GET  /tools  → liste des outils")
    logger.info("  GET  /logs   → historique consultations")
    logger.info("  GET  /health → santé")
    logger.info("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
