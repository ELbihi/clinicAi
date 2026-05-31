"""
report_agent.py — ReportAgent node.

MCP INTÉGRÉ :
  - mcp_get_icd()          → suggestion CIM-10 dans le rapport
  - mcp_log_consultation() → persistance du rapport final
"""
import logging
from datetime import datetime
from langchain_core.messages import AIMessage

from app.state import MedicalState
from app.llm_factory import llm_invoke
from app.tools.mcp_client import mcp_get_icd, mcp_log_consultation

logger = logging.getLogger(__name__)
SEP = "=" * 62


def _qa_text(qa_pairs: list) -> str:
    if not qa_pairs:
        return "  Aucun entretien disponible."
    return "\n".join(
        f"  Q{i+1}. {qa['question']}\n      → {qa['answer']}"
        for i, qa in enumerate(qa_pairs)
    )


def _detect_domain(text: str) -> str:
    t = text.lower()
    mapping = {
        "respiratoire":       ["toux", "dyspnée", "poumon", "bronche", "asthme"],
        "cardiaque":          ["thoracique", "cardiaque", "infarctus", "palpitation"],
        "neurologique":       ["céphalée", "migraine", "vertige", "paralysie"],
        "digestif":           ["abdomen", "diarrhée", "vomissement", "nausée"],
        "infectieux":         ["fièvre", "infection", "virus", "grippe"],
        "musculosquelettique":["douleur", "articulation", "dos", "muscle"],
    }
    for domain, kws in mapping.items():
        if any(k in t for k in kws):
            return domain
    return "général"


def report_agent_node(state: MedicalState) -> MedicalState:
    name      = state.get("patient_name", "Inconnu")
    age       = state.get("patient_age", "N/A")
    desc      = state.get("initial_description", "")
    summary   = state.get("diagnostic_summary", "")
    severity  = state.get("severity", "N/A")
    care      = state.get("interim_care", "")
    notes     = state.get("physician_notes", "") or "Aucune note."
    treatment = state.get("physician_treatment", "")
    qa_pairs  = state.get("qa_pairs", [])
    session   = state.get("session_id", "N/A")
    ts        = datetime.now().strftime("%d/%m/%Y à %H:%M")
    qa_fmt    = _qa_text(qa_pairs)

    # ── MCP Tool : suggestion CIM-10 pour le rapport ──────────────────────
    domain  = _detect_domain(f"{desc} {summary}")
    icd_ref = mcp_get_icd(domain)
    logger.info(f"[ReportAgent][MCP] ICD for '{domain}': {icd_ref[:60]}")

    # ── LLM : génération du rapport ───────────────────────────────────────
    prompt = f"""Tu es l'agent de rapport dans un système d'orientation clinique simulée (EXERCICE ACADÉMIQUE).

Génère un rapport clinique final structuré, professionnel, en français pour la session {session}.

Données :
- Patient : {name}, {age} ans | Date : {ts}
- Description initiale : {desc}
- Synthèse clinique préliminaire : {summary}
- Sévérité estimée : {severity}
- Référence CIM-10 (domaine {domain}, éducatif) : {icd_ref}
- Recommandation intermédiaire : {care}
- Notes médecin : {notes}
- Traitement proposé : {treatment}
- Entretien :
{qa_fmt}

Structure OBLIGATOIRE (respecte exactement) :

RAPPORT D'ORIENTATION CLINIQUE SIMULÉE
Session : {session} | Date : {ts}
{SEP}

1. INFORMATIONS PATIENT
2. MOTIF DE CONSULTATION
3. SYNTHÈSE CLINIQUE PRÉLIMINAIRE
4. ENTRETIEN DIAGNOSTIQUE (5 questions)
5. RÉFÉRENCE CLASSIFICATOIRE (CIM-10, éducatif uniquement)
6. RECOMMANDATION INTERMÉDIAIRE — Sévérité : {severity}
7. VALIDATION MÉDECIN TRAITANT
8. CONDUITE À TENIR / TRAITEMENT PROPOSÉ

{SEP}
AVERTISSEMENT ÉTHIQUE
⚠ Ce système ne remplace pas une consultation médicale.
Ce rapport est produit dans le cadre d'un exercice académique de simulation multi-agents.

Réponds directement avec le rapport, sans introduction."""

    result = llm_invoke(prompt, temperature=0.2)

    if result:
        final_report = result.strip()
        logger.info("[ReportAgent] LLM report OK.")
    else:
        final_report = f"""RAPPORT D'ORIENTATION CLINIQUE SIMULÉE
Session : {session} | Date : {ts}
{SEP}

1. INFORMATIONS PATIENT
   Nom    : {name}
   Âge    : {age} ans
   Session: {session}

2. MOTIF DE CONSULTATION
   {desc}

3. SYNTHÈSE CLINIQUE PRÉLIMINAIRE
   {summary}

4. ENTRETIEN DIAGNOSTIQUE (5 questions)
{qa_fmt}

5. RÉFÉRENCE CLASSIFICATOIRE (CIM-10, éducatif)
   Domaine : {domain}
   {icd_ref}

6. RECOMMANDATION INTERMÉDIAIRE — Sévérité : {severity}
   {care}

7. VALIDATION MÉDECIN TRAITANT
   Notes : {notes}

8. CONDUITE À TENIR / TRAITEMENT PROPOSÉ
   {treatment}

{SEP}
AVERTISSEMENT ÉTHIQUE
⚠ Ce système ne remplace pas une consultation médicale.
Exercice académique — simulation multi-agents (LangGraph/FastAPI/MCP)."""
        logger.info("[ReportAgent] Offline template used.")

    # ── MCP Tool : persistance du rapport final ────────────────────────────
    mcp_log_consultation(
        session_id=f"{session}-REPORT",
        patient_name=f"{name} ({age} ans)",
        severity=severity,
        summary=f"RAPPORT FINAL — {treatment[:150]}",
    )
    logger.info(f"[ReportAgent][MCP] Final report logged for session {session}")

    return {
        **state,
        "final_report": final_report,
        "messages": state.get("messages", []) + [
            AIMessage(content="Rapport final généré (MCP enrichi).", name="report_agent")
        ],
    }
