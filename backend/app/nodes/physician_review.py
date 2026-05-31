"""
physician_review.py — Human-in-the-Loop physician gate.

Le graph s'interrompt AVANT ce nœud.
Ce nœud s'exécute uniquement après que l'API ait injecté
physician_treatment + physician_validated=True via update_state.
"""
import logging
from langchain_core.messages import AIMessage
from app.state import MedicalState

logger = logging.getLogger(__name__)


def physician_review_node(state: MedicalState) -> MedicalState:
    validated = state.get("physician_validated", False)
    treatment = state.get("physician_treatment", "").strip()

    if validated and treatment:
        logger.info("[PhysicianReview] Validated — passing through to report.")
        return {
            **state,
            "messages": state.get("messages", []) + [
                AIMessage(content="Validation médecin enregistrée.", name="physician_review")
            ],
        }

    # Ne devrait pas arriver car interrupt_before empêche l'exécution
    # sans données injectées, mais par sécurité :
    logger.warning("[PhysicianReview] Reached without physician data — this shouldn't happen.")
    return state
