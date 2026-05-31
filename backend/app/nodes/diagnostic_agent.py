"""
diagnostic_agent.py — DiagnosticAgent node.

MCP INTÉGRÉ :
  - Avant chaque question → mcp_get_red_flags() pour enrichir l'analyse
  - Phase 2 synthèse      → mcp_lookup_symptom() pour info éducative
                           → mcp_get_icd() pour suggestion CIM-10
  - Fin de synthèse       → mcp_log_consultation() pour persistance

FLUX (inchangé) :
  q_count < 5  → retourne la question suivante (pas de LLM)
  q_count == 5 → génère la synthèse via LLM + enrichissement MCP
"""
import logging
from langchain_core.messages import AIMessage

from app.state import MedicalState
from app.tools.patient_tools import DIAGNOSTIC_QUESTIONS, MAX_QUESTIONS
from app.tools.care_tools import classify_severity, recommend_interim_care
from app.tools.mcp_client import (
    mcp_lookup_symptom,
    mcp_get_red_flags,
    mcp_get_icd,
    mcp_log_consultation,
)
from app.llm_factory import llm_invoke

logger = logging.getLogger(__name__)


def _detect_domain(text: str) -> str:
    """Detect clinical domain keyword for ICD suggestion."""
    t = text.lower()
    domains = {
        "respiratoire": ["toux", "dyspnée", "poumon", "bronche", "asthme", "pneumon"],
        "cardiaque":    ["thoracique", "cardiaque", "infarctus", "palpitation", "cœur"],
        "neurologique": ["céphalée", "migraine", "tête", "vertige", "paralysie", "convulsion"],
        "digestif":     ["abdomen", "diarrhée", "vomissement", "nausée", "estomac"],
        "infectieux":   ["fièvre", "infection", "virus", "bactérie", "grippe"],
        "musculosquelettique": ["douleur", "articulation", "dos", "muscle", "genou"],
    }
    for domain, keywords in domains.items():
        if any(kw in t for kw in keywords):
            return domain
    return "général"


def diagnostic_agent_node(state: MedicalState) -> MedicalState:
    q_count  = state.get("question_count", 0)
    qa_pairs = state.get("qa_pairs", [])
    name     = state.get("patient_name", "Patient")
    age      = state.get("patient_age", "")
    desc     = state.get("initial_description", "")
    session  = state.get("session_id", "N/A")

    # ── Phase 1 : retourner la question suivante ───────────────────────────
    if q_count < MAX_QUESTIONS:
        question = DIAGNOSTIC_QUESTIONS[q_count]
        logger.info(f"[DiagnosticAgent] Serving Q{q_count + 1}: {question[:60]}...")

        # MCP : récupérer les red flags pour contexte (log uniquement ici)
        red_flags = mcp_get_red_flags()
        logger.info(f"[DiagnosticAgent][MCP] {len(red_flags)} red-flag keywords loaded.")

        return {
            **state,
            "current_question": question,
            "messages": state.get("messages", []) + [
                AIMessage(content=question, name="diagnostic_agent")
            ],
        }

    # ── Phase 2 : synthèse après 5 réponses ───────────────────────────────
    logger.info(f"[DiagnosticAgent] All {MAX_QUESTIONS} answers received. Building synthesis...")

    qa_text = "\n".join(
        f"Q{i+1}: {qa['question']}\nRéponse: {qa['answer']}"
        for i, qa in enumerate(qa_pairs)
    )
    combined = f"{desc} {qa_text}"

    # ── Outils locaux : sévérité + recommandation ──────────────────────────
    severity = classify_severity.invoke({"symptoms_text": combined})
    if severity not in ("Bénin", "Modéré", "Urgent"):
        severity = "Modéré"
    interim_care = recommend_interim_care.invoke({"severity": severity})

    # ── MCP Tool 1 : info symptôme éducative ──────────────────────────────
    # Extraire le symptôme principal depuis la description
    main_symptom_kw = next(
        (w for w in ["toux", "fièvre", "douleur thoracique", "céphalée", "dyspnée",
                     "vomissement", "diarrhée", "fatigue"]
         if w in combined.lower()),
        "symptôme non spécifié"
    )
    mcp_symptom_info = mcp_lookup_symptom(main_symptom_kw)
    logger.info(f"[DiagnosticAgent][MCP] Symptom info retrieved for '{main_symptom_kw}'")

    # ── MCP Tool 2 : suggestion CIM-10 ────────────────────────────────────
    domain = _detect_domain(combined)
    mcp_icd = mcp_get_icd(domain)
    logger.info(f"[DiagnosticAgent][MCP] ICD suggestion for domain '{domain}': {mcp_icd[:50]}")

    # ── MCP Tool 3 : red flags (vérification finale) ──────────────────────
    red_flags = mcp_get_red_flags()
    detected_flags = [f for f in red_flags if f.lower() in combined.lower()]
    flags_note = (
        f"⚠ Signaux d'alarme détectés : {', '.join(detected_flags)}"
        if detected_flags else "Aucun signal d'alarme majeur identifié."
    )
    logger.info(f"[DiagnosticAgent][MCP] Red flags detected: {detected_flags}")

    # ── LLM : synthèse enrichie avec contexte MCP ─────────────────────────
    prompt = f"""Tu es un agent diagnostique dans un système multi-agents d'orientation clinique simulée (EXERCICE ACADÉMIQUE).

Patient : {name}, {age} ans
Description initiale : {desc}

Entretien diagnostique (5 Q/R) :
{qa_text}

Informations complémentaires issues des outils MCP :
- Info éducative sur le symptôme principal ({main_symptom_kw}) : {mcp_symptom_info}
- Suggestion de classification (CIM-10, domaine {domain}) : {mcp_icd}
- Analyse des signaux d'alarme : {flags_note}

Rédige une synthèse clinique préliminaire structurée (150-200 mots) en français :
1. Symptômes principaux identifiés
2. Facteurs de risque et signaux d'alarme
3. Éléments orientant la prise en charge
4. Rappel du cadre académique

N'émets pas de diagnostic définitif. Utilise : "orientation clinique préliminaire", "synthèse clinique".
Réponds directement, sans introduction."""

    result = llm_invoke(prompt, temperature=0.3)

    if result:
        diagnostic_summary = result.strip()
        logger.info("[DiagnosticAgent] LLM synthesis OK.")
    else:
        qa_bullets = "\n".join(f"  • {qa['answer']}" for qa in qa_pairs)
        diagnostic_summary = (
            f"Synthèse clinique préliminaire — {name} ({age} ans)\n\n"
            f"Description : {desc}\n\n"
            f"Réponses patient :\n{qa_bullets}\n\n"
            f"Info MCP — {main_symptom_kw} : {mcp_symptom_info}\n"
            f"CIM-10 ({domain}) : {mcp_icd}\n"
            f"{flags_note}\n\n"
            f"Sévérité estimée : {severity}.\n\n"
            f"⚠ Exercice académique — ne constitue pas un diagnostic médical."
        )
        logger.info("[DiagnosticAgent] Offline template used (no LLM).")

    # ── MCP Tool 4 : persistance de la consultation ────────────────────────
    mcp_log_consultation(
        session_id=session,
        patient_name=f"{name} ({age} ans)",
        severity=severity,
        summary=diagnostic_summary[:300],
    )
    logger.info(f"[DiagnosticAgent][MCP] Consultation logged for session {session}")

    return {
        **state,
        "diagnostic_summary": diagnostic_summary,
        "severity": severity,
        "interim_care": interim_care,
        "messages": state.get("messages", []) + [
            AIMessage(
                content=f"Synthèse générée (MCP enrichie). Sévérité : {severity}.",
                name="diagnostic_agent",
            )
        ],
    }
