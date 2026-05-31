"""
api.py — ClinAI FastAPI backend (version corrigée).

ARCHITECTURE DU FLUX :
  POST /consultation/start
    → Initialise l'état, lance le graph jusqu'au 1er interrupt
    → Le supervisor route vers diagnostic_agent
    → interrupt_before["diagnostic_agent"] stoppe le graph
    → On lit l'état et on retourne la Q1 au client

  POST /consultation/resume  (resume_type="patient_answer") × 5
    → Injecte {qa_pairs, question_count} dans l'état
    → Reprend le graph : supervisor → diagnostic_agent (Q suivante ou synthèse)
    → interrupt_before stoppe à nouveau après chaque question
    → Quand q_count==5 : diagnostic_agent génère la synthèse
    → supervisor route vers physician_review → interrupt_before stoppe

  POST /consultation/resume  (resume_type="physician_validation")
    → Injecte {physician_treatment, physician_notes, physician_validated=True}
    → Reprend : physician_review passe, supervisor → report_agent → FINISH

TIMEOUTS :
  - /start et /resume : timeout 60s sur le stream (LLM appel unique)
  - Le graph ne boucle JAMAIS — chaque stream() s'arrête sur interrupt ou END
"""
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.graph import get_graph
from app.state import MedicalState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ClinAI — Orientation Clinique Simulée",
    description="API multi-agents | EXERCICE ACADÉMIQUE",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Schemas ────────────────────────────────────────────────────────────────

class SessionStartResponse(BaseModel):
    session_id: str
    message: str

class ConsultationStartRequest(BaseModel):
    session_id: str
    patient_name: str
    patient_age: int = Field(ge=0, le=150)
    initial_description: str = Field(min_length=5)

class ConsultationStartResponse(BaseModel):
    thread_id: str
    status: str
    current_question: Optional[str] = None
    question_number: int = 1
    message: str

class ResumeRequest(BaseModel):
    thread_id: str
    resume_type: str           # "patient_answer" | "physician_validation"
    patient_answer: Optional[str] = None
    physician_notes: Optional[str] = None
    physician_treatment: Optional[str] = None

class ResumeResponse(BaseModel):
    thread_id: str
    status: str
    current_question: Optional[str] = None
    question_number: Optional[int] = None
    diagnostic_summary: Optional[str] = None
    severity: Optional[str] = None
    interim_care: Optional[str] = None
    message: str

class ConsultationStateResponse(BaseModel):
    thread_id: str
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    severity: Optional[str] = None
    question_count: Optional[int] = None
    diagnostic_summary: Optional[str] = None
    interim_care: Optional[str] = None
    physician_validated: Optional[bool] = None
    final_report: Optional[str] = None
    status: str

class ReportResponse(BaseModel):
    thread_id: str
    final_report: str
    severity: Optional[str] = None
    patient_name: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _get_state(thread_id: str) -> MedicalState:
    snap = get_graph().get_state(_cfg(thread_id))
    if not snap or not snap.values:
        raise HTTPException(404, f"Thread '{thread_id}' introuvable.")
    return snap.values


def _status(s: MedicalState) -> str:
    if s.get("final_report"):           return "completed"
    if s.get("physician_validated"):    return "generating_report"
    if s.get("diagnostic_summary"):     return "awaiting_physician"
    q = s.get("question_count", 0)
    return f"interviewing_q{q + 1}"


def _run_graph(thread_id: str, input_data):
    """
    Lance ou reprend le graph et s'arrête sur le prochain interrupt ou END.
    Retourne l'état final après l'exécution.
    Lève HTTPException(500) si le graph échoue.
    """
    graph = get_graph()
    config = _cfg(thread_id)
    try:
        # stream() s'arrête automatiquement sur interrupt_before ou END
        for chunk in graph.stream(input_data, config=config, stream_mode="values"):
            logger.debug(f"[Stream] chunk keys: {list(chunk.keys()) if chunk else 'none'}")
    except Exception as e:
        logger.error(f"[Graph] Error during stream: {e}", exc_info=True)
        raise HTTPException(500, f"Erreur interne du workflow : {e}")
    return _get_state(thread_id)


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.post("/sessions/start", response_model=SessionStartResponse, tags=["Sessions"])
async def sessions_start():
    sid = f"CLN-{uuid.uuid4().hex[:8].upper()}"
    logger.info(f"[API] New session: {sid}")
    return SessionStartResponse(session_id=sid, message="Session créée.")


@app.post("/consultation/start", response_model=ConsultationStartResponse, tags=["Consultation"])
async def consultation_start(req: ConsultationStartRequest):
    """
    Initialise le workflow.
    Le graph tourne jusqu'au 1er interrupt (avant diagnostic_agent).
    Retourne la Q1 sans aucun appel LLM → très rapide.
    """
    thread_id = f"{req.session_id}-{uuid.uuid4().hex[:6]}"
    logger.info(f"[API] /consultation/start thread={thread_id}")

    initial: MedicalState = {
        "patient_name": req.patient_name,
        "patient_age": req.patient_age,
        "initial_description": req.initial_description,
        "session_id": req.session_id,
        "question_count": 0,
        "qa_pairs": [],
        "messages": [],
        "physician_validated": False,
        "diagnostic_summary": "",
        "final_report": "",
    }

    # Lance : START → supervisor → [interrupt avant diagnostic_agent]
    # Aucun LLM appelé ici, doit être instantané
    state = _run_graph(thread_id, initial)

    # La question est dans state mais le nœud n'a pas encore tourné
    # (interrupt_before = avant diagnostic_agent).
    # On lit la Q1 directement depuis DIAGNOSTIC_QUESTIONS.
    from app.tools.patient_tools import DIAGNOSTIC_QUESTIONS
    q1 = DIAGNOSTIC_QUESTIONS[0]

    logger.info(f"[API] /start OK — Q1 ready for thread {thread_id}")
    return ConsultationStartResponse(
        thread_id=thread_id,
        status="interviewing_q1",
        current_question=q1,
        question_number=1,
        message=f"Consultation démarrée. Q1/5 : {q1}",
    )


@app.post("/consultation/resume", response_model=ResumeResponse, tags=["Consultation"])
async def consultation_resume(req: ResumeRequest):
    """
    Reprend le workflow après un interrupt.

    patient_answer :
      - Injecte la réponse + incrémente question_count
      - Reprend jusqu'au prochain interrupt
      - Si q_count atteint 5 → diagnostic_agent génère la synthèse (1 appel LLM)
        puis supervisor route vers physician_review → interrupt

    physician_validation :
      - Injecte le traitement médecin + validated=True
      - Reprend : physician_review passe, report_agent génère le rapport (1 appel LLM)
      - Graph termine (FINISH)
    """
    graph = get_graph()
    config = _cfg(req.thread_id)
    state = _get_state(req.thread_id)

    # ── Réponse patient ───────────────────────────────────────────────────
    if req.resume_type == "patient_answer":
        if not (req.patient_answer or "").strip():
            raise HTTPException(400, "patient_answer requis.")

        q_count  = state.get("question_count", 0)
        qa_pairs = list(state.get("qa_pairs", []))
        current_q = state.get("current_question") or ""

        # Si pas de question en cours (1er appel), lire depuis la liste
        if not current_q:
            from app.tools.patient_tools import DIAGNOSTIC_QUESTIONS
            current_q = DIAGNOSTIC_QUESTIONS[q_count] if q_count < 5 else ""

        qa_pairs.append({"question": current_q, "answer": req.patient_answer.strip()})
        new_count = q_count + 1

        logger.info(f"[API] Patient answer #{new_count} for thread {req.thread_id}")

        # Injecter dans l'état persisté
        graph.update_state(config, {
            "qa_pairs": qa_pairs,
            "question_count": new_count,
        })

        # Reprendre : supervisor → diagnostic_agent (Q suivante ou synthèse)
        # Si new_count < 5 → diagnostic_agent retourne la Q suivante, interrupt stoppe
        # Si new_count == 5 → diagnostic_agent appelle le LLM (synthèse), puis
        #   supervisor → physician_review → interrupt stoppe
        state = _run_graph(req.thread_id, None)
        st = _status(state)

        if st == "awaiting_physician":
            logger.info(f"[API] Synthesis done — awaiting physician for {req.thread_id}")
            return ResumeResponse(
                thread_id=req.thread_id,
                status=st,
                diagnostic_summary=state.get("diagnostic_summary"),
                severity=state.get("severity"),
                interim_care=state.get("interim_care"),
                message="Entretien terminé. Synthèse générée. En attente du médecin.",
            )

        # Question suivante
        nq = state.get("current_question")
        if not nq:
            from app.tools.patient_tools import DIAGNOSTIC_QUESTIONS
            qn = state.get("question_count", new_count)
            nq = DIAGNOSTIC_QUESTIONS[qn] if qn < 5 else None

        nqn = state.get("question_count", new_count)
        logger.info(f"[API] Q{nqn + 1} ready for thread {req.thread_id}")
        return ResumeResponse(
            thread_id=req.thread_id,
            status=st,
            current_question=nq,
            question_number=nqn + 1,
            message=f"Q{nqn + 1}/5 : {nq}",
        )

    # ── Validation médecin ────────────────────────────────────────────────
    elif req.resume_type == "physician_validation":
        if not (req.physician_treatment or "").strip():
            raise HTTPException(400, "physician_treatment requis.")

        logger.info(f"[API] Physician validation for thread {req.thread_id}")

        graph.update_state(config, {
            "physician_notes":     req.physician_notes or "",
            "physician_treatment": req.physician_treatment.strip(),
            "physician_validated": True,
        })

        # Reprendre : physician_review passe, supervisor → report_agent (1 LLM) → FINISH
        state = _run_graph(req.thread_id, None)

        return ResumeResponse(
            thread_id=req.thread_id,
            status=_status(state),
            diagnostic_summary=state.get("diagnostic_summary"),
            severity=state.get("severity"),
            message="Validation enregistrée. Rapport généré.",
        )

    else:
        raise HTTPException(400, "resume_type doit être 'patient_answer' ou 'physician_validation'.")


@app.get("/consultation/{thread_id}", response_model=ConsultationStateResponse, tags=["Consultation"])
async def get_consultation(thread_id: str):
    s = _get_state(thread_id)
    return ConsultationStateResponse(
        thread_id=thread_id,
        patient_name=s.get("patient_name"),
        patient_age=s.get("patient_age"),
        severity=s.get("severity"),
        question_count=s.get("question_count"),
        diagnostic_summary=s.get("diagnostic_summary"),
        interim_care=s.get("interim_care"),
        physician_validated=s.get("physician_validated"),
        final_report=s.get("final_report"),
        status=_status(s),
    )


@app.get("/consultation/{thread_id}/report", response_model=ReportResponse, tags=["Consultation"])
async def get_report(thread_id: str):
    s = _get_state(thread_id)
    report = s.get("final_report", "")
    if not report:
        raise HTTPException(404, "Rapport non disponible — consultation non terminée.")
    return ReportResponse(
        thread_id=thread_id,
        final_report=report,
        severity=s.get("severity"),
        patient_name=s.get("patient_name"),
    )


@app.get("/health", tags=["Infra"])
async def health():
    import os
    provider = (
        "Groq" if os.getenv("GROQ_API_KEY")
        else "Gemini" if os.getenv("GOOGLE_API_KEY")
        else "Offline/template"
    )
    return {"status": "ok", "service": "ClinAI", "version": "1.1.0", "llm_provider": provider}
