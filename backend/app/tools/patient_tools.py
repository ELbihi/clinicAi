from langchain_core.tools import tool

DIAGNOSTIC_QUESTIONS = [
    "Pouvez-vous décrire précisément vos symptômes principaux et depuis combien de temps ils sont apparus ?",
    "Avez-vous de la fièvre, des frissons ou des sueurs nocturnes récemment ?",
    "Prenez-vous actuellement des médicaments ou avez-vous des antécédents médicaux importants ?",
    "Avez-vous été en contact avec des personnes malades ou avez-vous voyagé récemment ?",
    "Comment évaluez-vous votre état général — pouvez-vous effectuer vos activités quotidiennes normalement ?",
]

MAX_QUESTIONS = 5


@tool
def ask_patient(question_index: int) -> str:
    """Retrieve the diagnostic question at the given index (0-based)."""
    if not (0 <= question_index < MAX_QUESTIONS):
        return f"Index invalide (0–{MAX_QUESTIONS-1})."
    return DIAGNOSTIC_QUESTIONS[question_index]


@tool
def validate_answer(answer: str) -> dict:
    """Check that a patient answer is non-empty and sufficiently detailed."""
    s = answer.strip()
    if not s:
        return {"valid": False, "message": "Réponse vide."}
    if len(s) < 5:
        return {"valid": False, "message": "Réponse trop courte."}
    return {"valid": True, "message": "Réponse enregistrée."}
