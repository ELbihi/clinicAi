# 🏥 ClinAI — Orientation Clinique Simulée
> **Mini-Projet Fin de Module SMA — LangGraph Multi-Agents**  
> Pr. MHAMMEDI Sajida | Université Mohammed Premier Oujda / ENIAD Berkane

---

## ⚠ Cadre Éthique
Exercice académique. Pas de diagnostic définitif. Ce rapport ne remplace pas une consultation médicale.

---

## ✅ Objectifs du cahier des charges — État complet

| # | Objectif | Statut | Où |
|---|----------|--------|----|
| 1 | Workflow multi-agents LangGraph | ✅ | `backend/app/graph.py` |
| 2 | État partagé entre agents | ✅ | `backend/app/state.py` (MedicalState TypedDict + MemorySaver) |
| 3 | Tools + Human-in-the-Loop | ✅ | `tools/` + `interrupt_before` × 2 |
| 4 | API FastAPI | ✅ | `backend/app/api.py` (5 endpoints) |
| 5 | **MCP intégré aux agents** | ✅ | `mcp_server/server.py` + `tools/mcp_client.py` — appelé par DiagnosticAgent et ReportAgent |
| 6 | Interface utilisateur | ✅ | `frontend/app.py` (Streamlit 4 écrans) |
| 7 | **LangGraph Studio** | ✅ | `langgraph.json` + `test_graph_studio.py` (3 cas complets) |

---

## 🔄 Workflow LangGraph

```
START → Supervisor
    │
    ▼  ← interrupt_before["diagnostic_agent"]
DiagnosticAgent (Q1) — MCP: get_red_flag_keywords
    ↑ API injecte réponse patient → reprend
DiagnosticAgent (Q2..Q4) — même flux
    ↑ API injecte réponse patient → reprend
DiagnosticAgent (Q5 + SYNTHÈSE LLM)
    — MCP: lookup_symptom_info
    — MCP: get_icd_suggestion
    — MCP: get_red_flag_keywords (vérification)
    — MCP: log_consultation (persistance)
    │
    ▼  ← interrupt_before["physician_review"]
PhysicianReview (HITL médecin)
    ↑ API injecte physician_treatment → reprend
    │
    ▼
ReportAgent (RAPPORT LLM)
    — MCP: get_icd_suggestion
    — MCP: log_consultation (rapport final)
    │
    ▼
Supervisor → FINISH
```

---

## 🔧 Architecture MCP

```
Agents LangGraph (diagnostic_agent, report_agent)
    │
    │  HTTP POST /call  (sync, timeout 5s, fallback auto)
    ▼
mcp_server/server.py — http://localhost:8001
    ├── POST /call              ← appel outil (agents)
    ├── GET  /tools             ← schéma MCP (Studio)
    ├── GET  /logs              ← historique consultations
    └── GET  /health            ← statut + nb outils

4 outils MCP :
  lookup_symptom_info    → info éducative symptôme
  get_icd_suggestion     → suggestion chapitre CIM-10
  get_red_flag_keywords  → liste signaux d'alarme
  log_consultation       → persistance JSON lines
```

---

## 🆓 LLM gratuits supportés

| Provider | Modèle | Lien | Limite gratuite |
|----------|--------|------|-----------------|
| **Groq** *(recommandé)* | `llama-3.3-70b-versatile` | https://console.groq.com | 14 400 req/jour |
| **Offline** | Template statique | *(aucune clé)* | Illimité |

---

## 🚀 Démarrage

### 1. Configuration
```bash
cp .env.example .env
# Éditer .env → ajouter GROQ_API_KEY=gsk_...
```

### 2. Installation
```bash
cd backend
pip install -r requirements.txt
```

### 3. Terminal 1 — MCP Server
```bash
cd mcp_server
python server.py
# → http://localhost:8001
# Vérifier : curl http://localhost:8001/health
# Tester  : curl http://localhost:8001/tools
# Logs    : curl http://localhost:8001/logs
```

### 4. Terminal 2 — FastAPI Backend
```bash
cd backend
python main.py
# → http://localhost:8000
# Swagger : http://localhost:8000/docs
```

### 5. Terminal 3 — Streamlit Frontend
```bash
cd frontend
streamlit run app.py
# → http://localhost:8501
```

---

## 🧪 LangGraph Studio

### Option A — Test local complet (recommandé)
```bash
cd backend

# Cas 1 seulement (rapide, ~30s sans LLM)
python test_graph_studio.py

# Les 3 cas complets
python test_graph_studio.py --all

# Rapports générés dans : backend/test_outputs/
```

### Option B — LangGraph Studio cloud
```bash
cd backend
pip install langgraph-cli
langgraph dev
# → Ouvrir https://smith.langchain.com/studio/
# → Sélectionner le graphe "clinai_graph"
# → Visualiser les nœuds, transitions, états intermédiaires
```

**Ce que Studio visualise :**
- Graphe avec 4 nœuds + edges conditionnels
- État MedicalState à chaque étape
- Points d'interruption (losanges oranges) sur `diagnostic_agent` et `physician_review`
- Historique des messages entre agents

---

## 📡 API — Référence rapide

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/sessions/start` | Créer une session |
| `POST` | `/consultation/start` | Démarrer le workflow |
| `POST` | `/consultation/resume` | Injecter réponse patient ou médecin |
| `GET` | `/consultation/{id}` | État courant |
| `GET` | `/consultation/{id}/report` | Rapport final |
| `GET` | `/health` | Santé + provider LLM actif |

---

## 🧪 Cas de test

| Cas | Patient | Description | Sévérité |
|-----|---------|-------------|----------|
| Cas 1 | Ahmed Benali, 34 ans | Syndrome respiratoire simple | Modéré |
| Cas 2 | Fatima Cherkaoui, 67 ans | Douleur thoracique + signaux d'alarme | Urgent |
| Cas 3 | Youssef Ait, 22 ans | Céphalées de tension — cas bénin | Bénin |
