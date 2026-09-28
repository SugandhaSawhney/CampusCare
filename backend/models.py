from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base, utcnow


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(40), unique=True, nullable=False)  # STUDENT, TRIAGE_AGENT, DEPARTMENT_STAFF, DEAN, ADMIN


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    program = Column(String(40))      # students: e.g. CSE
    batch_year = Column(Integer)      # students: e.g. 2027
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    role = relationship("Role")
    staff_profile = relationship("StaffProfile", back_populates="user", uselist=False)

    @property
    def role_name(self):
        return self.role.name if self.role else None

    @property
    def batch_label(self):
        return f"{self.program} {self.batch_year}" if self.program and self.batch_year else None


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    code = Column(String(12), unique=True, nullable=False)
    description = Column(String(255))
    is_sensitive = Column(Boolean, default=False)       # restricted-access department (Mental Health)
    is_emergency = Column(Boolean, default=False)       # uses emergency escalation path for CRITICAL cases
    capabilities = Column(JSON, default=list)           # skills/subcategories this department can resolve
    lead_id = Column(Integer, ForeignKey("users.id"))   # escalation level 2
    dean_id = Column(Integer, ForeignKey("users.id"))   # escalation level 3

    lead = relationship("User", foreign_keys=[lead_id])
    dean = relationship("User", foreign_keys=[dean_id])


class StaffProfile(Base):
    __tablename__ = "staff_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    skills = Column(JSON, default=list)
    available = Column(Boolean, default=True)
    max_active_cases = Column(Integer, default=12)
    hierarchy_level = Column(Integer, default=1)  # 1 staff, 2 lead, 3 dean, 4 central
    title = Column(String(80))

    user = relationship("User", back_populates="staff_profile")
    department = relationship("Department")


class CampusSupportRequest(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    request_number = Column(String(20), unique=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category_hint = Column(String(80))  # optional student-provided hint (never a department choice)

    category = Column(String(80))
    subcategory = Column(String(80))
    priority = Column(String(12), default="MEDIUM")
    priority_reason = Column(Text)
    sensitivity_level = Column(String(16), default="NORMAL")  # NORMAL | CONFIDENTIAL | HIGH
    privacy_mode = Column(String(16), default="NORMAL")       # NORMAL | CONFIDENTIAL | ANONYMOUS
    anonymous = Column(Boolean, default=False)
    scope = Column(String(16), default="INDIVIDUAL")
    batch_label = Column(String(40))
    deadline_hours = Column(Float)

    affected_count = Column(Integer, default=1)
    cluster_id = Column(Integer, ForeignKey("clusters.id"))

    ai_confidence = Column(Float)
    ai_engine = Column(String(20))
    ai_routing_reason = Column(Text)
    student_summary = Column(Text)      # student-safe explanation
    human_review_reason = Column(Text)
    required_skill = Column(String(80))

    primary_department_id = Column(Integer, ForeignKey("departments.id"))
    assigned_staff_id = Column(Integer, ForeignKey("users.id"))
    assigned_team_id = Column(Integer, ForeignKey("departments.id"))
    assignment_reason = Column(JSON)

    status = Column(String(30), default="NEW", index=True)
    sla_due_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    routed_at = Column(DateTime)
    resolved_at = Column(DateTime)
    resolution_note = Column(Text)
    resolution_confirmed = Column(Boolean, default=False)
    reopen_requested = Column(Boolean, default=False)

    escalation_level = Column(Integer, default=0)
    escalated_at = Column(DateTime)
    reassignment_count = Column(Integer, default=0)
    routing_history = Column(JSON, default=list)  # ordered list of department ids that owned the case
    embedding = Column(JSON)
    last_ai_analysis = Column(JSON)

    student = relationship("User", foreign_keys=[student_id])
    assigned_staff = relationship("User", foreign_keys=[assigned_staff_id])
    primary_department = relationship("Department", foreign_keys=[primary_department_id])
    departments = relationship("RequestDepartment", back_populates="request", cascade="all, delete-orphan")
    cluster = relationship("Cluster", foreign_keys=[cluster_id])

    @property
    def secondary_department_ids(self):
        return [d.department_id for d in self.departments if d.role == "SUPPORTING"]


class RequestDepartment(Base):
    """Links one canonical request to its owning + supporting departments (no duplicate tickets)."""
    __tablename__ = "request_departments"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    role = Column(String(12), nullable=False)  # PRIMARY | SUPPORTING
    reason = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("request_id", "department_id"),)

    request = relationship("CampusSupportRequest", back_populates="departments")
    department = relationship("Department")


class Cluster(Base):
    """Routing / impact-analysis layer only. Members stay independent requests."""
    __tablename__ = "clusters"
    id = Column(Integer, primary_key=True)
    label = Column(String(160), nullable=False)
    category = Column(String(80))
    subcategory = Column(String(80))
    primary_department_id = Column(Integer, ForeignKey("departments.id"))
    batch_label = Column(String(40))
    scope = Column(String(16), default="INDIVIDUAL")
    population_size = Column(Integer)
    status = Column(String(20), default="INVESTIGATING")
    priority = Column(String(12), default="MEDIUM")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    primary_department = relationship("Department")
    members = relationship("ClusterMember", back_populates="cluster", cascade="all, delete-orphan")


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    request_id = Column(Integer, ForeignKey("requests.id"), unique=True, nullable=False)
    similarity = Column(Float)
    method = Column(String(20))
    added_at = Column(DateTime, default=utcnow)

    cluster = relationship("Cluster", back_populates="members")
    request = relationship("CampusSupportRequest")


class SLARule(Base):
    __tablename__ = "sla_rules"
    id = Column(Integer, primary_key=True)
    priority = Column(String(12), unique=True, nullable=False)
    resolution_hours = Column(Float, nullable=False)
    escalation_window_hours = Column(Float, nullable=False)
    max_escalation_level = Column(Integer, nullable=False)


class SLARecord(Base):
    __tablename__ = "sla_records"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    priority = Column(String(12))
    started_at = Column(DateTime, default=utcnow)
    due_at = Column(DateTime)
    status = Column(String(16), default="WITHIN")  # WITHIN | APPROACHING | BREACHED | MET
    breached_at = Column(DateTime)
    level = Column(Integer, default=1)


class Escalation(Base):
    __tablename__ = "escalations"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    from_level = Column(Integer)
    to_level = Column(Integer)
    reason = Column(String(255))
    trigger = Column(String(30))  # SLA_BREACH | MANUAL | REASSIGNMENT | EMERGENCY
    target_user_id = Column(Integer, ForeignKey("users.id"))
    actor_id = Column(Integer, ForeignKey("users.id"))
    escalated_at = Column(DateTime, default=utcnow)
    closed = Column(Boolean, default=False)
    decision_note = Column(Text)
    closed_at = Column(DateTime)

    request = relationship("CampusSupportRequest")
    target_user = relationship("User", foreign_keys=[target_user_id])


class RoutingRule(Base):
    """Admin-editable keyword rules that feed the deterministic classifier."""
    __tablename__ = "routing_rules"
    id = Column(Integer, primary_key=True)
    keyword = Column(String(80), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    subcategory = Column(String(80), nullable=False)
    weight = Column(Float, default=2.0)
    active = Column(Boolean, default=True)

    department = relationship("Department")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"))
    actor_id = Column(Integer, ForeignKey("users.id"))  # null = SYSTEM
    action = Column(String(60), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    reason = Column(Text)
    timestamp = Column(DateTime, default=utcnow, index=True)

    actor = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"))
    message = Column(String(400), nullable=False)
    kind = Column(String(30), default="INFO")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class InternalNote(Base):
    """Staff-only. Never returned by student-facing APIs."""
    __tablename__ = "internal_notes"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    author = relationship("User")


class RequestMessage(Base):
    """Student-visible conversation thread."""
    __tablename__ = "request_messages"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_staff = Column(Boolean, default=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    author = relationship("User")
