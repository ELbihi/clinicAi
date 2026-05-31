"""
mcp_client.py — Client HTTP synchrone vers le MCP Server (port 8001).

Utilisé par diagnostic_agent.py et report_agent.py.
Fallback automatique si le serveur est hors ligne.
"""
import json
import logging
import requests
from typing import Any

logger = logging.getLogger("clinai.mcp.client")

MCP_CALL_URL = "http://localhost:8001/call"

_FALLBACKS: dict[str, Any] = {
    "lookup_symptom_info":   "Info symptôme non disponible (MCP hors ligne).",
    "get_icd_suggestion":    "Référence CIM-10 non disponible (MCP hors ligne).",
    "get_red_flag_keywords": [
        "douleur thoracique", "dyspnée au repos", "perte de conscience",
        "paralysie soudaine", "céphalée brutale", "confusion mentale",
        "fièvre > 40°C", "convulsions", "sueurs froides + douleur thoracique",
        "irradiation vers le bras gauche",
    ],
    "log_consultation":      "Log non enregistré (MCP hors ligne).",
}


def call_mcp_tool(tool_name: str, arguments: dict, timeout: int = 5) -> Any:
    """
    Appelle un outil du serveur MCP via HTTP POST /call.
    Retourne le résultat ou une valeur de fallback si le serveur est indisponible.
    """
    try:
        resp = requests.post(
            MCP_CALL_URL,
            json={"name": tool_name, "arguments": arguments},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        content = data.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            try:
                return json.loads(text)   # liste ou dict
            except (json.JSONDecodeError, TypeError):
                return text               # chaîne simple
        return data

    except requests.exceptions.ConnectionError:
        logger.warning(f"[MCP] Serveur inaccessible — fallback '{tool_name}'")
        return _FALLBACKS.get(tool_name, "MCP hors ligne.")
    except requests.exceptions.Timeout:
        logger.warning(f"[MCP] Timeout sur '{tool_name}' — fallback")
        return _FALLBACKS.get(tool_name, "MCP timeout.")
    except Exception as exc:
        logger.warning(f"[MCP] Erreur '{tool_name}': {exc} — fallback")
        return _FALLBACKS.get(tool_name, f"Erreur MCP: {exc}")


# ── Fonctions nommées utilisées par les agents ────────────────────────────

def mcp_lookup_symptom(symptom: str) -> str:
    r = call_mcp_tool("lookup_symptom_info", {"symptom": symptom})
    logger.info(f"[MCP] lookup_symptom_info('{symptom}') → {str(r)[:80]}")
    return str(r)


def mcp_get_red_flags() -> list:
    r = call_mcp_tool("get_red_flag_keywords", {})
    logger.info(f"[MCP] get_red_flag_keywords → {len(r) if isinstance(r, list) else '?'} items")
    return r if isinstance(r, list) else _FALLBACKS["get_red_flag_keywords"]


def mcp_get_icd(domain: str) -> str:
    r = call_mcp_tool("get_icd_suggestion", {"clinical_domain": domain})
    logger.info(f"[MCP] get_icd_suggestion('{domain}') → {str(r)[:80]}")
    return str(r)


def mcp_log_consultation(session_id: str, patient_name: str, severity: str, summary: str) -> str:
    r = call_mcp_tool("log_consultation", {
        "session_id":   session_id,
        "patient_name": patient_name,
        "severity":     severity,
        "summary":      summary[:300],
    })
    logger.info(f"[MCP] log_consultation('{session_id}') → {str(r)[:60]}")
    return str(r)
