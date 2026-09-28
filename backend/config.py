"""Central configuration. Every tunable routing/SLA/impact rule lives here (or in the DB for admin-editable rules)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database" / "campuscare.db"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-in-.env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# ---- LLM (optional). Any OpenAI-compatible endpoint works. ----
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "12"))

# ---- Confidence-aware routing ----
CONFIDENCE_AUTO_ROUTE = 0.85   # >= auto-route
CONFIDENCE_SUGGEST = 0.60      # 0.60-0.849 suggestion + human review; < 0.60 human triage, no suggestion applied

# ---- Clustering ----
CLUSTER_WINDOW_DAYS = int(os.getenv("CLUSTER_WINDOW_DAYS", "14"))
SIMILARITY_THRESHOLD_FALLBACK = float(os.getenv("SIMILARITY_THRESHOLD_FALLBACK", "0.60"))
SIMILARITY_THRESHOLD_EMBEDDING = float(os.getenv("SIMILARITY_THRESHOLD_EMBEDDING", "0.80"))
MIN_CLUSTER_DISPLAY = 2  # clusters with fewer members are not shown as "active clusters"

# Population sizes used for impact % (prototype values; replace with SIS data)
BATCH_SIZES = {"CSE 2027": 100, "CSE 2026": 110, "ECE 2027": 80, "ME 2027": 70, "ECE 2026": 75}
DEFAULT_BATCH_SIZE = 100
CLASS_SIZE = 60
DEPARTMENT_SIZE = 400
CAMPUS_SIZE = 5000

# ---- Impact-aware priority (configurable rules) ----
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
IMPACT_BUMP_AFFECTED_COUNT = 10     # >= this many affected students => +1 level
IMPACT_BUMP_AFFECTED_PCT = 25.0     # >= this % of population affected => +1 level
DEADLINE_BUMP_HOURS = 48            # deadline within this many hours => +1 level
MAX_IMPACT_PRIORITY = "HIGH"        # impact/deadline alone never makes a case CRITICAL
CAMPUS_WIDE_MIN_PRIORITY = "HIGH"

# ---- Assignment scoring weights (deterministic, NOT machine learning) ----
W_SKILL = 40
W_DEPARTMENT = 20
W_AVAILABILITY = 15
W_WORKLOAD = 25

# ---- SLA defaults (seeded into SLARule table; editable by admin). Prototype values, not institutional promises. ----
DEFAULT_SLA_RULES = {
    # priority: (resolution_hours, escalation_window_hours, max_escalation_level)
    "CRITICAL": (2, 1, 4),
    "HIGH": (8, 4, 4),
    "MEDIUM": (48, 24, 3),
    "LOW": (120, 48, 2),
}
SLA_APPROACHING_FRACTION = 0.25     # < 25% of window left => APPROACHING
EMERGENCY_DEPARTMENTS = {"Medical", "Campus Safety", "Mental Health / Counselling"}
REASSIGNMENT_ESCALATION_THRESHOLD = 3
SLA_CHECK_INTERVAL_SECONDS = 60

CRISIS_MESSAGE = (
    "If you are in immediate danger, please call 112 (national emergency) now. "
    "Tele-MANAS (14416) offers free 24x7 mental health support. "
    "A counsellor has been alerted to your request as a priority."
)

ESCALATION_LEVELS = {
    1: "Assigned Support Staff",
    2: "Department Lead / Supervisor",
    3: "Dean / Department Authority",
    4: "Central Student Administration",
}
