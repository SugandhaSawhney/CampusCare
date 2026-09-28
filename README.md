# CampusCare — AI-Powered Student Triage & Intelligent Support Routing

**Track 01: Student Triage & Routing.** One student, one real need: *"I have a problem and I don't know which office handles it."*
The student writes it once, in their own words. CampusCare works out where it belongs, whether it is sensitive, how many others are hit,
who should own it, and escalates it if nobody acts in time.

> CampusCare does not simply receive student complaints. It understands the request, determines where it belongs, decides whether it can
> safely be clustered, evaluates impact, routes it to the right department and available staff, keeps sensitive cases private, sends
> uncertain cases to humans, and escalates unresolved cases through the correct hierarchy.

## Folder structure
```
campuscare/
├── .env.example            # copy to .env (never commit .env)
├── README.md
├── database/               # SQLite file lives here (campuscare.db)
├── backend/
│   ├── requirements.txt
│   ├── main.py             # FastAPI app, CORS, SLA background loop
│   ├── config.py           # thresholds, weights, SLA defaults, batch sizes
│   ├── database.py         # engine / session
│   ├── models.py           # all SQLAlchemy models
│   ├── security.py         # PBKDF2 hashing, JWT, role guards
│   ├── access.py           # RBAC scoping + role-safe serialization
│   ├── seed.py             # demo data
│   ├── services/
│   │   ├── routing_engine.py   # triage → cluster → priority → route → assign → SLA → escalate
│   │   ├── ai_classifier.py    # LLM call + Pydantic validation + rule fallback
│   │   ├── rule_classifier.py  # deterministic classifier (no API key needed)
│   │   └── similarity.py       # embeddings + cosine, or text/category fallback
│   └── routers/ auth.py requests.py triage.py staff.py admin.py
└── frontend/               # React + Vite + Tailwind + Recharts
    └── src/ api.js auth.jsx App.jsx components/ pages/
```

## Setup & run
Requirements: Python 3.10+, Node 18+.

```bash
# 1. Environment
cp .env.example .env            # optional: add OPENAI_API_KEY; app works without it

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                  # creates tables in ../database/campuscare.db + seeds demo data (re-run to reset)
uvicorn main:app --reload --port 8000     # API docs: http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173  (proxies /api → :8000)
```
Tables are also auto-created on backend start (`init_db`), but `seed.py` is the database initialization + seed command for the demo.

## Environment variables (.env)
| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key. Change it. |
| `OPENAI_API_KEY` / `LLM_API_KEY` | Optional. If absent → deterministic rule classifier + text similarity. |
| `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL` | Any OpenAI-compatible endpoint (default `gpt-4o-mini`). |
| `DEMO_MODE` | `true` enables the "simulate SLA breach" demo button. |
| `SIMILARITY_THRESHOLD_FALLBACK`, `SIMILARITY_THRESHOLD_EMBEDDING`, `CLUSTER_WINDOW_DAYS` | Clustering tuning (0.60 / 0.80 / 14). Confidence bands 0.85 / 0.60 live in `backend/config.py`. |
| `CORS_ORIGINS`, `JWT_EXPIRE_MINUTES` | Frontend origins, token lifetime. |

## Test credentials (all passwords: `Campus@123`)
| Role | Username | What to show |
|---|---|---|
| Student | `student01` (CSE 2027) — also `student02…student20` | submit, track, reopen |
| Triage agent | `triage.priya` | human triage queue, overrides |
| Department staff | `fin.anita` (Finance), `it.kiran` (IT), `acad.vikram` (Academics) | own dept only |
| Department lead (L2) | `fin.lead`, `it.lead`, `acad.lead` … | receives L2 escalations |
| Counsellor (restricted) | `mh.rao` | sees mental-health cases; others can't |
| Dean (L3) | `dean.academic` (IT/Acad/Fin/Placement), `dean.welfare` (MH/Med/Hostel/Disability/Safety) | escalations only |
| Central admin (L4) | `central.admin` | top of hierarchy |
| Admin | `admin` | everything + audit log |

## Demo flow (≈5 minutes)
1. **Student triage** — log in as `student01` → *Get support* → paste:
   *"Our CSE 2027 batch is unable to complete fee payment for course registration. The payment portal keeps failing and the registration deadline is tomorrow."*
   → **AI Triage Complete**: Finance / Scholarship (primary) + IT Services (supporting), Fee Payment, BATCH, HIGH, ~96% confidence, reason shown. No department picker.
2. **Routing view** — log in as `fin.anita` or `triage.priya` → open the new case: route trace, cluster **Fee Payment Failure ~12 / 100 CSE 2027 students (12%)**, priority raised with reason (deadline + impact), assignment reason ("required skill matched + lowest active workload") and candidate score table.
3. **Clusters** — `/staff/clusters` → the fee cluster lists 12 separate cases, each with its own ID, SLA and status. Never merged.
4. **Escalation** — as `triage.priya` click **Demo: simulate SLA breach** → escalates L1 → L2 (`fin.lead` notified). Click again → L3 `dean.academic`. Log in as the dean → *Oversight* → **Decide** → close with decision note.
5. **Low confidence** — `triage.priya` → *Human triage* → open the ~43% ambiguous case → correct department/subcategory, give reason → assigned. Override appears in the audit trail and *Admin → Routing feedback*.
6. **Sensitive / anonymous** — as a student submit something like *"I've been feeling hopeless and can't cope"* with **Anonymous** → routed straight to Mental Health, restricted, no clustering, crisis contacts shown. `fin.anita` / `triage.priya` can't see it; `mh.rao` sees it with identity hidden.
7. **Routing mismatch** — the seeded LMS case bounced IT → Academics → IT shows "Potential routing rule mismatch detected".

## How it works

**Routing architecture.** All decisions live in `services/routing_engine.py`, not in route handlers. Pipeline on submit:
`classify_request` (LLM or rules, plus admin keyword rules) → `determine_sensitivity` → `determine_scope` → cluster check (`find_similar_cases` / `create_or_attach_cluster`, non-sensitive only) → `calculate_priority` (base urgency + deadline ≤48h + affected ≥10 or ≥25% of population; capped at HIGH unless emergency) → confidence gate (≥0.85 auto-route; 0.60–0.849 suggestion + human verification; <0.60 human triage) → `select_primary_department` / `select_secondary_departments` (one canonical request, `RequestDepartment` rows PRIMARY/SUPPORTING) → `find_eligible_staff` + `calculate_assignment_score` (skill 40 + department 20 + availability 15 + workload 25 — deterministic and shown, not ML) → `start_sla` → human-readable explanation stored on the request.

**RBAC.** Enforced in the backend on every endpoint: JWT → user re-loaded from DB (role not trusted from token) → `require_roles` → `access.scoped_query` / `can_view` for row-level scope. Students: own requests only, student-safe projection (no AI internals, notes, scoring, clusters). Triage: non-restricted cases. Department staff: own/supporting department only; restricted cases only if assigned or lead. Dean: cases escalated into their departments (≥L2; restricted only ≥L3). Admin: all. The React route guards only mirror this for UX. Token is kept in `sessionStorage`; no case data stored client-side.

**AI fallback.** With a key, the LLM gets a strict-JSON prompt listing the only allowed departments/subcategories/enums; the reply is validated with Pydantic `Literal` types. Any failure (no key, network, invalid JSON, invalid enum) falls back to the deterministic weighted-keyword classifier, which also runs alongside the LLM as a safety net that can only *raise* care (sensitivity, crisis, emergency) and sends LLM/rule disagreements to human review. The engine used is shown on every case.

**Clustering.** Only NORMAL-sensitivity requests from the last 14 days. With embeddings: cosine ≥ 0.80. Without: normalized-token Jaccard (with synonyms) blended with category/subcategory match ≥ 0.60. A `Cluster` is an impact layer linking independent requests via `ClusterMember`; each request keeps its own student, SLA, status and resolution. Impact = distinct affected students / population (batch size, class 60, department 400, campus 5000) — the system never invents cases for students who didn't report. Attaching a case recomputes cluster priority and raises open members' priority with the reason.

**Sensitive / anonymous routing.** Mental-health signals, harassment, or sensitivity HIGH → bypass clustering, go straight to Mental Health / Counselling, excluded from cluster analytics (aggregate count only), invisible to triage and unrelated departments. Crisis wording triggers CRITICAL priority and immediate crisis contacts for the student. Anonymous mode: DB keeps the linkage for integrity, but staff APIs return "Anonymous student (identity protected)"; the student tracks it via their authenticated portal and request ID. Confidential mode: Medical/Disability default.

**SLA escalation.** SLA rules per priority (admin-editable). States: within / approaching (inside the warning window) / breached. A background loop (every 60 s, plus on dashboard load) runs `check_sla`: on breach → status ESCALATED, `Escalation` record, notify next authority, escalation level +1, new window, audit log. Path: L1 staff → L2 department lead → L3 dean → L4 central administration, capped per priority (LOW stops at L2). Critical medical/safety cases use the emergency path straight to L3. Three reassignments also auto-escalate. The authority closes the escalation with a decision note.

## Notes
- Built as a hackathon prototype: SLA hours are illustrative, not institutional promises.
- No external email: notifications are in-app.
