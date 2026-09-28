from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, iso
from models import AuditLog, Department, Role, RoutingRule, SLARule, StaffProfile, User
from security import hash_password, require_roles
from services.routing_engine import active_case_count

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles("ADMIN")


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.]+$")
    full_name: str
    email: str
    password: str = Field(min_length=8)
    role: Literal["STUDENT", "TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"]
    department_id: Optional[int] = None
    skills: List[str] = []
    hierarchy_level: int = 1
    title: Optional[str] = None


class UserPatch(BaseModel):
    role: Optional[Literal["STUDENT", "TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"]] = None
    department_id: Optional[int] = None
    skills: Optional[List[str]] = None
    available: Optional[bool] = None
    max_active_cases: Optional[int] = None
    hierarchy_level: Optional[int] = None
    is_active: Optional[bool] = None


class DeptPatch(BaseModel):
    lead_id: Optional[int] = None
    dean_id: Optional[int] = None
    capabilities: Optional[List[str]] = None
    is_emergency: Optional[bool] = None


class RuleIn(BaseModel):
    keyword: str = Field(min_length=2, max_length=80)
    department_id: int
    subcategory: str
    weight: float = Field(default=2.0, ge=0.5, le=10)


class SLAPatch(BaseModel):
    resolution_hours: float = Field(gt=0)
    escalation_window_hours: float = Field(gt=0)
    max_escalation_level: int = Field(ge=2, le=4)


def u_out(db, u):
    sp = u.staff_profile
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role_name,
            "is_active": u.is_active, "batch": u.batch_label,
            "department": sp.department.name if sp and sp.department else None, "department_id": sp.department_id if sp else None,
            "skills": sp.skills if sp else [], "available": sp.available if sp else None,
            "hierarchy_level": sp.hierarchy_level if sp else None, "title": sp.title if sp else None,
            "active_cases": active_case_count(db, u.id) if sp else None}


def log(db, actor, action, old=None, new=None, reason=None):
    db.add(AuditLog(actor_id=actor.id, action=action, old_value=old, new_value=new, reason=reason))


@router.get("/users")
def users(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [u_out(db, u) for u in db.query(User).order_by(User.role_id, User.id).all()]


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.query(User).filter((User.username == body.username) | (User.email == body.email)).first():
        raise HTTPException(400, "Username/email exists")
    role = db.query(Role).filter_by(name=body.role).first()
    u = User(username=body.username, full_name=body.full_name, email=body.email, password_hash=hash_password(body.password), role_id=role.id)
    db.add(u)
    db.flush()
    if body.role != "STUDENT":
        db.add(StaffProfile(user_id=u.id, department_id=body.department_id, skills=body.skills,
                            hierarchy_level=body.hierarchy_level, title=body.title))
    log(db, user, "USER_CREATED", None, f"{u.username}:{body.role}")
    db.commit()
    return u_out(db, u)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if body.role:
        log(db, user, "ROLE_CHANGED", u.role_name, body.role, u.username)
        u.role_id = db.query(Role).filter_by(name=body.role).first().id
    if body.is_active is not None:
        u.is_active = body.is_active
    sp = u.staff_profile
    if any(v is not None for v in (body.department_id, body.skills, body.available, body.max_active_cases, body.hierarchy_level)):
        if not sp:
            sp = StaffProfile(user_id=u.id)
            db.add(sp)
        for f in ("department_id", "skills", "available", "max_active_cases", "hierarchy_level"):
            v = getattr(body, f)
            if v is not None:
                setattr(sp, f, v)
        log(db, user, "STAFF_PROFILE_UPDATED", None, body.model_dump_json(exclude_none=True), u.username)
    db.commit()
    db.refresh(u)
    return u_out(db, u)


@router.get("/departments")
def departments(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"id": d.id, "name": d.name, "code": d.code, "is_sensitive": d.is_sensitive, "is_emergency": d.is_emergency,
             "capabilities": d.capabilities, "lead": d.lead.full_name if d.lead else None, "lead_id": d.lead_id,
             "dean": d.dean.full_name if d.dean else None, "dean_id": d.dean_id,
             "staff_count": db.query(StaffProfile).filter_by(department_id=d.id).count()} for d in db.query(Department).order_by(Department.id)]


@router.put("/departments/{dept_id}")
def update_department(dept_id: int, body: DeptPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    d = db.get(Department, dept_id)
    if not d:
        raise HTTPException(404, "Department not found")
    for f, v in body.model_dump(exclude_none=True).items():
        log(db, user, f"DEPARTMENT_{f.upper()}_CHANGED", str(getattr(d, f)), str(v), d.name)
        setattr(d, f, v)
    db.commit()
    return {"ok": True}


@router.get("/routing-rules")
def rules(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"id": r.id, "keyword": r.keyword, "department": r.department.name, "department_id": r.department_id,
             "subcategory": r.subcategory, "weight": r.weight, "active": r.active} for r in db.query(RoutingRule).all()]


@router.post("/routing-rules")
def add_rule(body: RuleIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    r = RoutingRule(**body.model_dump())
    db.add(r)
    log(db, user, "ROUTING_RULE_ADDED", None, f"{body.keyword}->{body.department_id}/{body.subcategory}")
    db.commit()
    return {"id": r.id}


@router.delete("/routing-rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    r = db.get(RoutingRule, rule_id)
    if r:
        log(db, user, "ROUTING_RULE_DELETED", r.keyword, None)
        db.delete(r)
        db.commit()
    return {"ok": True}


@router.get("/sla-rules")
def sla_rules(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"priority": r.priority, "resolution_hours": r.resolution_hours, "escalation_window_hours": r.escalation_window_hours,
             "max_escalation_level": r.max_escalation_level} for r in db.query(SLARule).all()]


@router.put("/sla-rules/{priority}")
def put_sla(priority: str, body: SLAPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    r = db.query(SLARule).filter_by(priority=priority).first()
    if not r:
        raise HTTPException(404, "Unknown priority")
    log(db, user, "SLA_RULE_CHANGED", f"{r.resolution_hours}/{r.escalation_window_hours}/{r.max_escalation_level}",
        f"{body.resolution_hours}/{body.escalation_window_hours}/{body.max_escalation_level}", priority)
    r.resolution_hours, r.escalation_window_hours, r.max_escalation_level = body.resolution_hours, body.escalation_window_hours, body.max_escalation_level
    db.commit()
    return {"ok": True}


@router.get("/audit-logs")
def audit_logs(limit: int = 200, action: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    return [{"id": l.id, "request_id": l.request_id, "actor": l.actor.full_name if l.actor else "SYSTEM", "action": l.action,
             "old": l.old_value, "new": l.new_value, "reason": l.reason, "at": iso(l.timestamp)}
            for l in q.order_by(AuditLog.timestamp.desc()).limit(min(limit, 1000)).all()]


@router.get("/routing-feedback")
def routing_feedback(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Human corrections of AI routing, aggregated: the raw material for improving routing rules."""
    rows = db.query(AuditLog).filter(AuditLog.action.in_(["OVERRIDE_PRIMARY_DEPARTMENT", "REASSIGN_DEPARTMENT", "ROUTING_MISMATCH"])).all()
    names = {d.id: d.name for d in db.query(Department).all()}
    agg = {}
    for l in rows:
        o = names.get(int(l.old_value), l.old_value) if (l.old_value or "").isdigit() else l.old_value
        n = names.get(int(l.new_value), l.new_value) if (l.new_value or "").isdigit() else l.new_value
        key = (l.action, o or "Unrouted", n or "")
        agg[key] = agg.get(key, 0) + 1
    return [{"action": k[0], "from": k[1], "to": k[2], "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
