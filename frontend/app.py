"""
app.py — ClinAI Streamlit Frontend (flux corrigé).

Timeouts API :
  /start   : 15s  (pas de LLM — juste initialisation)
  /resume  (patient_answer Q1-Q4) : 15s  (pas de LLM)
  /resume  (patient_answer Q5)    : 60s  (1 appel LLM — synthèse)
  /resume  (physician_validation) : 60s  (1 appel LLM — rapport)
  /report  : 10s
"""
import time
import streamlit as st
import requests

API = "http://localhost:8000"

st.set_page_config(page_title="ClinAI", page_icon="🏥", layout="wide")

st.markdown("""
<style>
  [data-testid="stSidebar"] { background: #0f172a !important; }
  [data-testid="stSidebar"] * { color: rgba(255,255,255,0.85) !important; }
  .ethics-pill {
    background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;
    border-radius: 20px; padding: 4px 14px; font-size: 0.75rem; font-weight: 600;
  }
  .agent-bubble {
    background: #eff6ff; border-left: 3px solid #0d9488;
    border-radius: 0 10px 10px 10px; padding: 10px 14px;
    margin: 6px 0; font-size: 0.88rem; max-width: 78%;
  }
  .patient-bubble {
    background: white; border: 2px solid #0d9488;
    border-radius: 10px 10px 0 10px; padding: 10px 14px;
    margin: 6px 0 6px auto; font-size: 0.88rem; max-width: 78%;
    text-align: right;
  }
  .synthesis-box {
    background: #f8fafc; border-left: 4px solid #0d9488;
    border-radius: 0 8px 8px 0; padding: 14px; font-size: 0.85rem;
    line-height: 1.7; max-height: 320px; overflow-y: auto;
  }
  .report-box {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 20px; font-family: monospace; font-size: 0.82rem;
    white-space: pre-wrap; max-height: 480px; overflow-y: auto;
  }
  .ethics-box-red {
    background: #fee2e2; border: 2px solid #ef4444; border-radius: 8px;
    padding: 10px 14px; color: #991b1b; font-weight: 600; margin-top: 12px;
  }
  .sev-urgent { color: #991b1b; font-weight: 700; font-size: 1.1rem; }
  .sev-modere { color: #92400e; font-weight: 700; font-size: 1.1rem; }
  .sev-benin  { color: #15803d; font-weight: 700; font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

# ── State init ─────────────────────────────────────────────────────────────
DEFAULTS = dict(
    screen=1, session_id=None, thread_id=None,
    patient_name="", patient_age=30, patient_desc="",
    q_number=1, current_question="", qa_history=[],
    diagnostic_summary="", severity="", interim_care="",
    final_report="",
)
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

QUICK = {
    "🤧 Syndrome respiratoire": ("Ahmed Benali", 34,
        "Toux sèche depuis 5 jours, fièvre légère (38 °C), fatigue, léger mal de gorge. Pas de dyspnée sévère."),
    "🚨 Signaux d'alarme": ("Fatima Cherkaoui", 67,
        "Douleur thoracique oppressante irradiant vers le bras gauche, sueurs froides, nausées, dyspnée depuis 2 h. ATCD HTA."),
    "😌 Cas bénin": ("Youssef Ait", 22,
        "Maux de tête modérés depuis 2 jours après travail prolongé sur écran. Pas de fièvre. Légère fatigue."),
}


# ── Sidebar ────────────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("## 🏥 ClinAI")
        st.caption("Orientation Clinique Simulée")
        st.divider()
        for i, lbl in enumerate(["Saisie patient", "Entretien", "Revue médecin", "Rapport final"], 1):
            icon = "✅" if i < st.session_state.screen else ("🔵" if i == st.session_state.screen else "⬜")
            st.markdown(f"{icon} **{i}. {lbl}**")
        st.divider()
        if st.session_state.session_id:
            st.caption(f"Session : `{st.session_state.session_id}`")
        st.divider()
        if st.button("🔄 Nouvelle consultation", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


sidebar()

# ── Topbar ─────────────────────────────────────────────────────────────────
c1, c2 = st.columns([3, 2])
with c1:
    st.markdown("# 🏥 ClinAI")
with c2:
    st.markdown(
        '<div style="text-align:right;padding-top:14px">'
        '<span class="ethics-pill">⚠ Exercice académique — Ne remplace pas un médecin</span>'
        '</div>', unsafe_allow_html=True)
st.divider()


# ── API helpers ────────────────────────────────────────────────────────────
def post(path, data, timeout=15):
    """POST avec timeout adaptatif. Affiche l'erreur dans l'UI."""
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Backend inaccessible. Lancez `python main.py` dans /backend.")
    except requests.exceptions.Timeout:
        st.error(f"⏱ Timeout ({timeout}s). Le LLM est peut-être lent — réessayez.")
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        st.error(f"Erreur API : {detail}")
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
    return None


def get(path, timeout=10):
    try:
        r = requests.get(f"{API}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erreur : {e}")
    return None


def timeout_for_resume(q_number: int, resume_type: str) -> int:
    """
    Timeout adaptatif :
    - Q1-Q4 (pas de LLM) : 15s
    - Q5 (LLM synthèse)  : 90s
    - physician           : 90s
    """
    if resume_type == "physician_validation":
        return 90
    return 90 if q_number >= 5 else 15


# ══════════════════════════════════════════════════════════════════════════
# Screen 1 — Patient Intake
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.screen == 1:
    st.subheader("Nouvelle consultation")

    st.markdown("**Cas de test rapides**")
    cols = st.columns(3)
    for i, (lbl, (nm, ag, ds)) in enumerate(QUICK.items()):
        with cols[i]:
            if st.button(lbl, use_container_width=True):
                st.session_state.patient_name = nm
                st.session_state.patient_age = ag
                st.session_state.patient_desc = ds
                st.rerun()

    st.markdown("")
    ca, cb = st.columns([3, 1])
    with ca:
        name = st.text_input("Nom du patient fictif",
                             value=st.session_state.patient_name,
                             placeholder="Ex : Mohammed Alami")
    with cb:
        age = st.number_input("Âge", 1, 120, value=int(st.session_state.patient_age))

    desc = st.text_area("Description initiale du cas",
                        value=st.session_state.patient_desc, height=130,
                        placeholder="Ex : Toux sèche persistante depuis 3 jours, fièvre légère...")

    st.markdown("")
    if st.button("Démarrer la consultation →", type="primary", use_container_width=True):
        if not name.strip() or not desc.strip():
            st.warning("Nom et description requis.")
        else:
            with st.spinner("Création de la session..."):
                sess = post("/sessions/start", {}, timeout=5)
            if sess:
                st.session_state.session_id = sess["session_id"]
                st.session_state.patient_name = name.strip()
                st.session_state.patient_age  = age
                st.session_state.patient_desc = desc.strip()

                # /start est rapide (pas de LLM) — timeout 15s
                with st.spinner("Initialisation du workflow multi-agents..."):
                    resp = post("/consultation/start", {
                        "session_id":          sess["session_id"],
                        "patient_name":        name.strip(),
                        "patient_age":         age,
                        "initial_description": desc.strip(),
                    }, timeout=15)

                if resp:
                    st.session_state.thread_id        = resp["thread_id"]
                    st.session_state.current_question = resp.get("current_question", "")
                    st.session_state.q_number         = resp.get("question_number", 1)
                    st.session_state.screen           = 2
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# Screen 2 — Patient Interview
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.screen == 2:
    st.subheader(f"Entretien patient — {st.session_state.patient_name}")

    qn = st.session_state.q_number
    st.progress((qn - 1) / 5, text=f"Question {min(qn, 5)} / 5")

    # Indication si Q5 va prendre plus de temps
    if qn == 5:
        st.info("ℹ La question 5 déclenche la génération de synthèse par le LLM — peut prendre 10-30s.")

    st.markdown("")

    # Historique chat
    for qa in st.session_state.qa_history:
        st.markdown(
            f'<div class="agent-bubble">🤖 <b>Agent Diagnostique</b><br>{qa["question"]}</div>',
            unsafe_allow_html=True)
        st.markdown(
            f'<div class="patient-bubble">👤 <b>Patient</b><br>{qa["answer"]}</div>',
            unsafe_allow_html=True)

    # Question courante
    if st.session_state.current_question:
        st.markdown(
            f'<div class="agent-bubble">🤖 <b>Question {qn}</b><br>'
            f'{st.session_state.current_question}</div>',
            unsafe_allow_html=True)

    answer = st.text_area("Réponse du patient :", height=100, key=f"ans_{qn}",
                          placeholder="Saisir la réponse du patient...")

    spinner_msg = (
        "Génération de la synthèse clinique par le LLM (peut prendre 20-30s)..."
        if qn >= 5 else "Envoi de la réponse..."
    )

    if st.button("Envoyer la réponse →", type="primary", use_container_width=True):
        if not answer.strip():
            st.warning("Veuillez saisir une réponse.")
        else:
            t = timeout_for_resume(qn, "patient_answer")
            with st.spinner(spinner_msg):
                resp = post("/consultation/resume", {
                    "thread_id":     st.session_state.thread_id,
                    "resume_type":   "patient_answer",
                    "patient_answer": answer.strip(),
                }, timeout=t)

            if resp:
                st.session_state.qa_history.append({
                    "question": st.session_state.current_question,
                    "answer":   answer.strip(),
                })
                if resp["status"] == "awaiting_physician":
                    st.session_state.diagnostic_summary = resp.get("diagnostic_summary", "")
                    st.session_state.severity           = resp.get("severity", "")
                    st.session_state.interim_care       = resp.get("interim_care", "")
                    st.session_state.screen             = 3
                else:
                    st.session_state.current_question = resp.get("current_question", "")
                    st.session_state.q_number         = resp.get("question_number", qn + 1)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# Screen 3 — Physician Review (HITL)
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.screen == 3:
    st.warning("🔒 En attente de la validation du médecin traitant")
    st.markdown("")

    col_l, col_r = st.columns([6, 4])

    with col_l:
        st.markdown("**Synthèse clinique préliminaire**")
        st.markdown(
            f'<div class="synthesis-box">'
            f'{st.session_state.diagnostic_summary or "En cours..."}'
            f'</div>', unsafe_allow_html=True)

    with col_r:
        st.markdown("**Recommandation intermédiaire**")
        sev = st.session_state.severity or "N/A"
        emoji = {"Urgent": "🔴", "Modéré": "🟡", "Bénin": "🟢"}.get(sev, "⚪")
        cls   = {"Urgent": "sev-urgent", "Modéré": "sev-modere", "Bénin": "sev-benin"}.get(sev, "")
        st.markdown(f'<p class="{cls}">{emoji} {sev}</p>', unsafe_allow_html=True)
        if st.session_state.interim_care:
            st.info(st.session_state.interim_care)

    st.divider()
    st.markdown("**Saisie du médecin traitant**")
    notes = st.text_area("Notes du médecin (optionnel)", height=80,
                         placeholder="Observations complémentaires...")
    treatment = st.text_area(
        "Conduite à tenir / Traitement proposé *", height=120,
        placeholder="Ex : Repos 3 j, paracétamol 1 g/6 h, bilan NFS-CRP, réévaluation 48 h...")

    st.info("ℹ La génération du rapport final peut prendre 10-30s (1 appel LLM).")

    if st.button("Valider et générer le rapport ✓", type="primary",
                 use_container_width=True, disabled=not treatment.strip()):
        with st.spinner("Génération du rapport final par le LLM..."):
            resp = post("/consultation/resume", {
                "thread_id":           st.session_state.thread_id,
                "resume_type":         "physician_validation",
                "physician_notes":     notes,
                "physician_treatment": treatment,
            }, timeout=90)

        if resp:
            time.sleep(0.3)
            r = get(f"/consultation/{st.session_state.thread_id}/report", timeout=10)
            if r:
                st.session_state.final_report = r.get("final_report", "")
                st.session_state.screen       = 4
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# Screen 4 — Final Report
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.screen == 4:
    st.success(f"✓ Rapport généré — Session {st.session_state.session_id}")
    st.markdown("")

    st.markdown(
        f'<div class="report-box">{st.session_state.final_report}</div>',
        unsafe_allow_html=True)

    st.markdown(
        '<div class="ethics-box-red">'
        '⚠ Ce système ne remplace pas une consultation médicale. '
        "Exercice académique de simulation multi-agents."
        '</div>', unsafe_allow_html=True)

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇ Télécharger le rapport (.txt)",
            data=st.session_state.final_report,
            file_name=f"clinai_{st.session_state.session_id}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with c2:
        if st.button("🔄 Nouvelle consultation", type="primary", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    with st.expander("📋 Historique de l'entretien"):
        for i, qa in enumerate(st.session_state.qa_history):
            st.markdown(f"**Q{i+1}.** {qa['question']}")
            st.markdown(f"> {qa['answer']}")
            st.divider()
