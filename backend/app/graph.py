"""
graph.py — ClinAI LangGraph workflow.

ARCHITECTURE CORRIGÉE :
  - interrupt_before=["diagnostic_agent", "physician_review"]
  - Le graph s'arrête AVANT chaque nœud critique
  - L'API reprend avec les données injectées via update_state
  - Aucune boucle infinie possible
"""
import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.state import MedicalState
from app.nodes.supervisor import supervisor_node
from app.nodes.diagnostic_agent import diagnostic_agent_node
from app.nodes.physician_review import physician_review_node
from app.nodes.report_agent import report_agent_node

logger = logging.getLogger(__name__)


def _route(state: MedicalState) -> str:
    nxt = state.get("next", "diagnostic_agent")
    logger.info(f"[Router] → {nxt}")
    return nxt


def build_graph():
    builder = StateGraph(MedicalState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("diagnostic_agent", diagnostic_agent_node)
    builder.add_node("physician_review", physician_review_node)
    builder.add_node("report_agent", report_agent_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor", _route,
        {
            "diagnostic_agent": "diagnostic_agent",
            "physician_review": "physician_review",
            "report_agent": "report_agent",
            "FINISH": END,
        },
    )
    # Après chaque agent → retour supervisor
    builder.add_edge("diagnostic_agent", "supervisor")
    builder.add_edge("physician_review", "supervisor")
    builder.add_edge("report_agent", "supervisor")

    graph = builder.compile(
        checkpointer=MemorySaver(),
        # CRITIQUE : interrompre AVANT ces deux nœuds
        # - diagnostic_agent : attend la réponse patient
        # - physician_review  : attend la validation médecin
        interrupt_before=["diagnostic_agent", "physician_review"],
    )
    logger.info("[Graph] Compiled with interrupt_before=['diagnostic_agent','physician_review']")
    return graph


_instance = None

def get_graph():
    global _instance
    if _instance is None:
        _instance = build_graph()
    return _instance
