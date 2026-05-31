from typing import Annotated, List, Optional
from typing_extensions import TypedDict, Literal
from langgraph.graph.message import add_messages


class QAPair(TypedDict):
    question: str
    answer: str


class MedicalState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    next: Literal["diagnostic_agent", "physician_review", "report_agent", "FINISH"]

    # Patient info
    patient_name: str
    patient_age: int
    initial_description: str
    session_id: str

    # Diagnostic
    question_count: int
    qa_pairs: List[QAPair]
    current_question: str

    # Outputs
    interim_care: str
    diagnostic_summary: str
    severity: Literal["Bénin", "Modéré", "Urgent"]

    # Physician HITL
    physician_notes: str
    physician_treatment: str
    physician_validated: bool

    # Final
    final_report: str
    error: Optional[str]
