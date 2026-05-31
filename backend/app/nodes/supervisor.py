"""
supervisor.py — Supervisor node.

LOGIQUE CORRIGÉE :
  q_count < 5  → diagnostic_agent (toujours, même avant la 1ère question)
  q_count == 5 et pas de summary → diagnostic_agent (pour générer la synthèse)
  summary présent et pas validé  → physician_review
  validé et pas de rapport       → report_agent
  rapport présent                → FINISH
"""
import logging
from langchain_core.messages import AIMessage
from app.state import MedicalState

logger = logging.getLogger(__name__)

MAX_Q = 5


def supervisor_node(state: MedicalState) -> MedicalState:
    q_count        = state.get("question_count", 0)
    has_summary    = bool(state.get("diagnostic_summary", "").strip())
    validated      = state.get("physician_validated", False)
    has_report     = bool(state.get("final_report", "").strip())

    if has_report:
        nxt = "FINISH"
    elif validated:
        nxt = "report_agent"
    elif has_summary:
        nxt = "physician_review"
    else:
        # Pas encore de synthèse → toujours vers diagnostic_agent
        # (que ce soit pour poser une question ou générer la synthèse)
        nxt = "diagnostic_agent"

    logger.info(
        f"[Supervisor] q={q_count} summary={has_summary} "
        f"validated={validated} report={has_report} → {nxt}"
    )

    return {
        **state,
        "next": nxt,
        "messages": state.get("messages", []) + [
            AIMessage(content=f"[Supervisor] → {nxt}", name="supervisor")
        ],
    }
