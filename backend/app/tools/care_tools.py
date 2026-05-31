from langchain_core.tools import tool
from typing import Literal

URGENT_KW = [
    "douleur thoracique", "dyspnée sévère", "perte de conscience", "paralysie",
    "céphalée brutale", "hémoptysie", "sang dans les selles", "confusion",
    "sueurs froides", "irradiation bras gauche", "anaphylaxie", "convulsions",
    "bras gauche", "oppressante", "irradiation",
]
MODERE_KW = [
    "fièvre", "toux persistante", "essoufflement", "vomissements", "diarrhée",
    "infection", "douleur abdominale", "migraine", "arthralgie", "palpitations",
]

CARE = {
    "Bénin": (
        "Repos à domicile 24–48 h. Hydratation suffisante (1,5–2 L/jour). "
        "Surveillance des symptômes. Consulter si aggravation ou persistance > 72 h."
    ),
    "Modéré": (
        "Repos et arrêt des activités physiques intenses. Hydratation et alimentation légère. "
        "Antipyrétiques si fièvre > 38,5 °C (selon antécédents). "
        "Consultation médicale recommandée sous 24–48 h. "
        "Appeler le 15 en cas d'aggravation rapide."
    ),
    "Urgent": (
        "Consultation médicale URGENTE ou appel du SAMU (15) immédiat. "
        "Ne pas rester seul. Éviter tout effort. "
        "Les symptômes décrits nécessitent une évaluation médicale immédiate."
    ),
}


@tool
def classify_severity(symptoms_text: str) -> str:
    """Classify clinical severity (Bénin / Modéré / Urgent) from symptom text."""
    t = symptoms_text.lower()
    if any(k in t for k in URGENT_KW):
        return "Urgent"
    if any(k in t for k in MODERE_KW):
        return "Modéré"
    return "Bénin"


@tool
def recommend_interim_care(severity: Literal["Bénin", "Modéré", "Urgent"]) -> str:
    """Return a standardised interim care recommendation for the given severity."""
    return CARE.get(severity, CARE["Modéré"])
