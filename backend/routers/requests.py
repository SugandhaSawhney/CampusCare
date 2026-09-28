from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from access import get_viewable, is_staff_view, serialize_detail, staff_dept_id
from database import get_db, utcnow
from models import AuditLog, CampusSupportRequest, InternalNote, RequestMessage, User
from security import get_current_user, require_roles
from services import routing_engine as eng

router = APIRouter(prefix="/requests", tags=["requests"])


class NewRequest(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    category_hint: Optional[str] = Field(default=None, max_length=80)  # optional hint; NOT a department choice
    privacy_mode: Literal["NORMAL", "CONFIDENTIAL", "ANONYMOUS"] = "NORMAL"


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    request_info: bool = False  # staff: mark WAITING_FOR_STUDENT


class StatusIn(BaseModel):
    status: Literal["IN_PROGRESS", "WAITING_FOR_STUDENT", "RESOLVED", "CLOSED"]
    note: Optional[str] = Field(default=None, max_length=2000)


class PriorityIn(BaseModel):
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason: str = Field(min_length=3, max_length=500)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class EscalateIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def require_owner_dept_or_authority(db, user, req):
    role = user.role_name
    if role in ("ADMIN", "DEAN"):
        return
    if role == "DEPARTMENT_STAFF" and req.primary_department_id == staff_dept_id(user):
        return
    raise HTTPException(403, "Only the owning department, dean or admin can do this")


@router.post("")
def create(body: NewRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("STUDENT"))):
    req = eng.create_request(db, user, body.title, body.description, body.privacy_mode, body.category_hint)
    return serialize_detail(db, req, user)


@router.get("/my")
def my_requests(db: Session = Depends(get_db), user: User = Depends(require_roles("STUDENT"))):
    reqs = db.query(CampusSupportRequest).filter_by(student_id=user.id).order_by(CampusSupportRequest.created_at.desc()).all()
    out = []
    for r in reqs:
        d = serialize_detail(db, r, user)
        out.append({k: d[k] for k in ("id", "request_number", "title", "status", "priority", "category", "primary_department",
                                      "created_at", "updated_at", "sla", "privacy_mode", "human_review")})
    return out


@router.get("/{request_id}")
def detail(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return serialize_detail(db, get_viewable(db, user, request_id), user)


@router.post("/{request_id}/message")
def message(request_id: int, body: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = get_viewable(db, user, request_id)
    staff = is_staff_view(user)
    db.add(RequestMessage(request_id=req.id, author_id=user.id, from_staff=staff, body=body.body))
    if staff:
        if body.request_info:
            eng.audit(db, req, user, "STATUS_CHANGE", req.status, "WAITING_FOR_STUDENT", "Requested information")
            req.status = "WAITING_FOR_STUDENT"
        eng.notify(db, req.student_id, req, f"New update on {req.request_number}", "MESSAGE")
    else:
        if req.status == "WAITING_FOR_STUDENT":
            eng.audit(db, req, user, "STATUS_CHANGE", req.status, "IN_PROGRESS", "Student replied")
            req.status = "IN_PROGRESS"
        eng.notify(db, req.assigned_staff_id, req, f"Student follow-up on {req.request_number}", "MESSAGE")
    req.updated_at = utcnow()
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/reopen")
def reopen(request_id: int, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(require_roles("STUDENT"))):
    req = get_viewable(db, user, request_id)
    if req.status not in ("RESOLVED", "CLOSED"):
        raise HTTPException(400, "Only resolved requests can be reopened")
    eng.audit(db, req, user, "STATUS_CHANGE", req.status, "REOPENED", body.body)
    req.status, req.reopen_requested, req.resolution_confirmed = "REOPENED", True, False
    db.add(RequestMessage(request_id=req.id, author_id=user.id, from_staff=False, body=f"Reopen request: {body.body}"))
    hours, _, _ = eng.sla_rule(db, req.priority)
    req.sla_due_at = utcnow() + timedelta(hours=hours)
    req.escalated_at = utcnow()  # new SLA window starts now
    eng.notify(db, req.assigned_staff_id, req, f"{req.request_number} was reopened by the student", "REOPEN")
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/confirm")
def confirm(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("STUDENT"))):
    req = get_viewable(db, user, request_id)
    if req.status != "RESOLVED":
        raise HTTPException(400, "Request is not resolved")
    eng.audit(db, req, user, "STATUS_CHANGE", "RESOLVED", "CLOSED", "Student confirmed resolution")
    req.status, req.resolution_confirmed = "CLOSED", True
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/status")
def set_status(request_id: int, body: StatusIn, db: Session = Depends(get_db),
               user: User = Depends(require_roles("DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    require_owner_dept_or_authority(db, user, req)
    if req.status in ("AWAITING_HUMAN_REVIEW", "NEW", "TRIAGING"):
        raise HTTPException(400, "Case must be assigned first")
    eng.audit(db, req, user, "STATUS_CHANGE", req.status, body.status, body.note)
    req.status = body.status
    if body.status == "RESOLVED":
        req.resolved_at, req.resolution_note = utcnow(), body.note
        eng.notify(db, req.student_id, req, f"{req.request_number} resolved. Please confirm or reopen.", "RESOLVED")
    if body.note and body.status == "RESOLVED":
        db.add(RequestMessage(request_id=req.id, author_id=user.id, from_staff=True, body=f"Resolution: {body.note}"))
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/priority")
def set_priority(request_id: int, body: PriorityIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if user.role_name == "DEPARTMENT_STAFF":
        require_owner_dept_or_authority(db, user, req)
    eng.audit(db, req, user, "PRIORITY_CHANGE", req.priority, body.priority, body.reason)
    req.priority, req.priority_reason = body.priority, f"Set to {body.priority} by {user.full_name}: {body.reason}"
    eng.start_sla(db, req)
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/notes")
def add_note(request_id: int, body: NoteIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    db.add(InternalNote(request_id=req.id, author_id=user.id, body=body.body))
    eng.audit(db, req, user, "INTERNAL_NOTE", None, None, "Internal note added")
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/{request_id}/escalate")
def escalate(request_id: int, body: EscalateIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if user.role_name == "DEPARTMENT_STAFF":
        require_owner_dept_or_authority(db, user, req)
    if (req.escalation_level or 1) >= 4:
        raise HTTPException(400, "Already at the highest escalation level")
    esc = eng.escalate_request(db, req, "MANUAL", body.reason, user)
    if not esc:
        raise HTTPException(400, "Could not escalate")
    db.commit()
    return serialize_detail(db, req, user)


@router.get("/{request_id}/audit")
def audit_trail(request_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    logs = db.query(AuditLog).filter_by(request_id=req.id).order_by(AuditLog.timestamp).all()
    from database import iso
    return [{"id": l.id, "action": l.action, "actor": l.actor.full_name if l.actor else "SYSTEM", "old": l.old_value,
             "new": l.new_value, "reason": l.reason, "at": iso(l.timestamp)} for l in logs]
