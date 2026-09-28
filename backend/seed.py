"""Reset and seed the CampusCare demo database.  Usage:  python seed.py"""
from datetime import timedelta

import config
from database import Base, SessionLocal, engine, utcnow
from models import CampusSupportRequest, Department, InternalNote, RequestMessage, Role, SLARule, StaffProfile, User
from security import hash_password
from services import routing_engine as eng
from services.rule_classifier import SUBCATEGORIES

DEMO_PASSWORD = "Campus@123"

DEPTS = [
    ("IT Services", "IT", False, False), ("Mental Health / Counselling", "MH", True, True), ("Academics", "ACAD", False, False),
    ("Finance / Scholarship", "FIN", False, False), ("Medical", "MED", False, True), ("Hostel", "HOS", False, False),
    ("Placement", "PLC", False, False), ("Disability Support", "DIS", False, False), ("Campus Safety", "SAFE", False, True),
]

STAFF = [  # username, name, role, dept code, level, skills, title
    ("triage.priya", "Priya Nair", "TRIAGE_AGENT", None, 1, [], "Student Support Triage"),
    ("triage.arjun", "Arjun Mehta", "TRIAGE_AGENT", None, 1, [], "Student Support Triage"),
    ("it.kiran", "Kiran Rao", "DEPARTMENT_STAFF", "IT", 1, ["Portal Access", "Email & Accounts"], "IT Support Engineer"),
    ("it.sameer", "Sameer Khan", "DEPARTMENT_STAFF", "IT", 1, ["Network / Wi-Fi", "Portal Access", "Software / LMS"], "IT Support Engineer"),
    ("it.lead", "Nisha Kapoor", "DEPARTMENT_STAFF", "IT", 2, SUBCATEGORIES["IT Services"], "IT Service Desk Lead"),
    ("mh.rao", "Dr. Leela Rao", "DEPARTMENT_STAFF", "MH", 1, ["Counselling Request", "Stress & Anxiety", "Crisis Support"], "Counsellor"),
    ("mh.farah", "Farah Siddiqui", "DEPARTMENT_STAFF", "MH", 1, ["Counselling Request", "Stress & Anxiety"], "Counsellor"),
    ("mh.lead", "Dr. Ravi Iyer", "DEPARTMENT_STAFF", "MH", 2, SUBCATEGORIES["Mental Health / Counselling"], "Head of Counselling"),
    ("acad.vikram", "Vikram Joshi", "DEPARTMENT_STAFF", "ACAD", 1, ["Course Registration", "Timetable"], "Academic Office"),
    ("acad.sneha", "Sneha Pillai", "DEPARTMENT_STAFF", "ACAD", 1, ["Course Registration", "Exams & Grades"], "Academic Office"),
    ("acad.rohit", "Rohit Das", "DEPARTMENT_STAFF", "ACAD", 1, ["Exams & Grades", "Attendance"], "Examinations Office"),
    ("acad.lead", "Prof. Anjali Menon", "DEPARTMENT_STAFF", "ACAD", 2, SUBCATEGORIES["Academics"], "Associate Registrar"),
    ("fin.anita", "Anita Desai", "DEPARTMENT_STAFF", "FIN", 1, ["Fee Payment", "Fee Discrepancy"], "Accounts Officer"),
    ("fin.rahul", "Rahul Bansal", "DEPARTMENT_STAFF", "FIN", 1, ["Fee Payment", "Refund"], "Accounts Officer"),
    ("fin.meera", "Meera Shah", "DEPARTMENT_STAFF", "FIN", 1, ["Scholarship", "Refund"], "Scholarship Officer"),
    ("fin.lead", "Suresh Gupta", "DEPARTMENT_STAFF", "FIN", 2, SUBCATEGORIES["Finance / Scholarship"], "Finance Manager"),
    ("med.khan", "Dr. Imran Khan", "DEPARTMENT_STAFF", "MED", 1, SUBCATEGORIES["Medical"], "Medical Officer"),
    ("med.lead", "Dr. Ritu Bose", "DEPARTMENT_STAFF", "MED", 2, SUBCATEGORIES["Medical"], "Chief Medical Officer"),
    ("hostel.ramesh", "Ramesh Yadav", "DEPARTMENT_STAFF", "HOS", 1, SUBCATEGORIES["Hostel"], "Hostel Supervisor"),
    ("hostel.lead", "Harpreet Gill", "DEPARTMENT_STAFF", "HOS", 2, SUBCATEGORIES["Hostel"], "Chief Warden"),
    ("place.tanya", "Tanya Arora", "DEPARTMENT_STAFF", "PLC", 1, SUBCATEGORIES["Placement"], "Placement Coordinator"),
    ("place.lead", "Dev Malhotra", "DEPARTMENT_STAFF", "PLC", 2, SUBCATEGORIES["Placement"], "Head of Placements"),
    ("dis.leena", "Leena Thomas", "DEPARTMENT_STAFF", "DIS", 1, SUBCATEGORIES["Disability Support"], "Accessibility Officer"),
    ("dis.lead", "Dr. Paul Mathew", "DEPARTMENT_STAFF", "DIS", 2, SUBCATEGORIES["Disability Support"], "Disability Services Lead"),
    ("safety.balbir", "Balbir Singh", "DEPARTMENT_STAFF", "SAFE", 1, SUBCATEGORIES["Campus Safety"], "Security Officer"),
    ("safety.lead", "Maj. Karan Sethi", "DEPARTMENT_STAFF", "SAFE", 2, SUBCATEGORIES["Campus Safety"], "Chief Security Officer"),
    ("dean.academic", "Prof. Kavita Sharma", "DEAN", None, 3, [], "Dean of Academic Affairs"),
    ("dean.welfare", "Dr. Anil Verma", "DEAN", None, 3, [], "Dean of Student Welfare"),
    ("central.admin", "Central Student Administration", "DEAN", None, 4, [], "Registrar's Office"),
    ("admin", "System Administrator", "ADMIN", None, 4, [], "Platform Admin"),
]
DEAN_OF = {"dean.academic": ["IT", "ACAD", "FIN", "PLC"], "dean.welfare": ["MH", "MED", "HOS", "DIS", "SAFE"]}

STUDENTS = ["Aarav Sharma", "Diya Patel", "Ishaan Gupta", "Ananya Reddy", "Vivaan Singh", "Saanvi Iyer", "Aditya Kumar",
            "Myra Joshi", "Reyansh Nair", "Kiara Menon", "Arnav Bhat", "Aisha Khan", "Kabir Malhotra", "Zara Fernandes",
            "Rohan Verma", "Tara Kapoor", "Dhruv Chauhan", "Nisha Rawat", "Yash Agarwal", "Meher Sandhu"]

FEE_TEXTS = [
    ("Fee payment failed", "My semester fee payment failed on the portal but money was deducted from my account."),
    ("Unable to pay semester fees", "I am unable to pay my semester fees, the payment page shows an error every time."),
    ("Fee portal payment error", "Fee portal payment error after entering card details. Payment not going through."),
    ("Semester fee payment not going through", "Tried paying the semester fee three times, payment keeps failing at the gateway."),
    ("Payment failed but amount deducted", "Fee payment failed yesterday and the amount was deducted. Portal still shows fee pending."),
    ("Cannot complete fee payment", "I cannot complete fee payment, the UPI payment fails on the fee portal."),
    ("Fee payment error on portal", "Getting a payment error on the fee portal when paying semester fees."),
    ("Fees not getting paid", "My fees payment is failing on the student fee portal since morning."),
    ("Fee payment stuck", "Fee payment stuck on processing and then failed. Please help, fee pending."),
    ("Online fee payment failing", "Online fee payment failing with error code. Net banking payment for fees failed."),
    ("Fee payment gateway error", "Fee payment gateway error, the semester fee payment page crashes."),
]
IT_TEXTS = [
    ("Cannot login to student portal", "I cannot login to the student portal, it says invalid password even after reset."),
    ("Student portal login not working", "Student portal login is not working for me, password reset OTP never arrives."),
    ("Portal access issue", "Unable to access the student portal since yesterday, login page keeps loading."),
    ("Login error on student portal", "Login error on the student portal. Cannot access my timetable or password page."),
]
ACAD_TEXTS = [
    ("Cannot register for electives", "I cannot register for my elective courses, course registration shows no seats."),
    ("Course registration problem", "Course registration page does not let me add the elective course, credits show zero."),
    ("Course registration blocked", "My course registration is blocked and I cannot enrol in electives this semester."),
]


def ago(**kw):
    return utcnow() - timedelta(**kw)


def run():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    roles = {n: Role(name=n) for n in ["STUDENT", "TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"]}
    db.add_all(roles.values())
    for p, (h, w, m) in config.DEFAULT_SLA_RULES.items():
        db.add(SLARule(priority=p, resolution_hours=h, escalation_window_hours=w, max_escalation_level=m))
    depts = {}
    for name, code, sens, emerg in DEPTS:
        depts[code] = Department(name=name, code=code, is_sensitive=sens, is_emergency=emerg, capabilities=SUBCATEGORIES[name],
                                 description=f"{name} support")
        db.add(depts[code])
    db.flush()
    pw = hash_password(DEMO_PASSWORD)  # one hash reused for speed; each real user would get its own salt
    users = {}
    for uname, name, role, dcode, level, skills, title in STAFF:
        u = User(username=uname, full_name=name, email=f"{uname}@campuscare.edu", password_hash=pw, role_id=roles[role].id)
        db.add(u)
        db.flush()
        db.add(StaffProfile(user_id=u.id, department_id=depts[dcode].id if dcode else None, skills=skills, hierarchy_level=level,
                            title=title, max_active_cases=12))
        users[uname] = u
        if dcode and level == 2:
            depts[dcode].lead_id = u.id
    for dean, codes in DEAN_OF.items():
        for c in codes:
            depts[c].dean_id = users[dean].id
    students = []
    for i, name in enumerate(STUDENTS, 1):
        prog, year = ("CSE", 2027) if i <= 14 else ("ECE", 2027) if i <= 17 else ("ME", 2027)
        u = User(username=f"student{i:02d}", full_name=name, email=f"student{i:02d}@campuscare.edu", password_hash=pw,
                 role_id=roles["STUDENT"].id, program=prog, batch_year=year)
        db.add(u)
        students.append(u)
    db.commit()

    def make(stu, title, desc, privacy="NORMAL", minutes_ago=60, routed_after_s=3):
        r = eng.create_request(db, stu, title, desc, privacy, created_at=ago(minutes=minutes_ago))
        if r.routed_at:
            r.routed_at = r.created_at + timedelta(seconds=routed_after_s)
        db.commit()
        return r

    # 1/12/13. Fee Payment Failure cluster (11 independent CSE-2027 cases, within last ~5h)
    for i, (t, d) in enumerate(FEE_TEXTS):
        make(students[i + 1], t, d, minutes_ago=300 - i * 22)
    # IT portal cluster
    for i, (t, d) in enumerate(IT_TEXTS):
        make(students[(i + 5) % 20], t, d, minutes_ago=900 - i * 60)
    # Academics registration cluster
    for i, (t, d) in enumerate(ACAD_TEXTS):
        make(students[i + 14], t, d, minutes_ago=600 - i * 45)

    make(students[3], "Scholarship application not submitting", "My merit scholarship application form is not submitting. I want to know the status of my scholarship.", minutes_ago=400)
    make(students[4], "Hostel room tap leaking", "The tap in my hostel room (Block B, 214) has been leaking for two days and needs plumbing repair.", minutes_ago=500)
    make(students[6], "Placement registration issue", "My placement registration for the upcoming company drive shows incomplete even though I uploaded my resume.", minutes_ago=200)
    make(students[7], "Doctor appointment needed", "I have had a fever and sore throat for three days and need a doctor appointment at the health centre.", minutes_ago=150)
    make(students[8], "Exam accommodation for dyslexia", "I have dyslexia and need extra time and a scribe for the end-semester exams. What documents are required?", minutes_ago=700)
    make(students[9], "Streetlights off near Block C", "Safety concern: the streetlights on the path near Block C have been off all week and it feels unsafe at night.", minutes_ago=240)
    mh = make(students[10], "Would like to talk to a counsellor", "I have been feeling overwhelmed and anxious for weeks and I can't sleep. I would like to book a counselling session.", "CONFIDENTIAL", minutes_ago=180)
    anon = make(students[11], "Being harassed by a senior", "A senior in my hostel keeps harassing me and I feel anxious going back to my room. I don't want my name shared.", "ANONYMOUS", minutes_ago=120)
    # 14. Low-confidence ambiguous requests -> human triage queue
    make(students[12], "Need help with something", "Something happened last week and I'm not sure who handles this. Need help sorting it out before next week.", minutes_ago=95)
    make(students[13], "Problem with my documents", "There is a problem with my documents and nobody is replying to me. Please guide me on what to do.", minutes_ago=70)
    # 16. Multi-department request
    make(students[16], "Course registration payment failing for our batch", "Course registration payment is failing for my batch. The registration payment page shows an error for many students in ECE 2027.", minutes_ago=110)

    # 15. SLA-breached cases: Academics (-> Lead), Finance scholarship HIGH (-> Lead -> Dean)
    grade = make(students[17], "Grade missing in transcript", "My grade for Data Structures is missing in my transcript and marks were not updated.", minutes_ago=60 * 55)
    schol = make(students[18], "Scholarship stipend not credited", "My scholarship stipend has not been credited and the scholarship renewal deadline is tomorrow.", minutes_ago=60 * 20)
    eng.check_sla(db)
    db.refresh(schol)
    schol.sla_due_at = ago(minutes=5)
    db.commit()
    eng.check_sla(db)

    # Reassignment ping-pong (routing-rule mismatch): IT -> Academics -> IT
    bounce = make(students[19], "LMS not showing my course", "The LMS (Moodle) does not show my enrolled course, so I cannot see the assignments.", minutes_ago=800)
    eng.reassign(db, bounce, users["it.kiran"], depts["ACAD"].id, None, "Enrolment data comes from Academics")
    eng.reassign(db, bounce, users["acad.vikram"], depts["IT"].id, None, "Enrolment is correct; LMS sync issue")

    # A worked case with messages + internal notes, and a closed case
    wifi = make(students[0], "Wi-Fi not working in library", "The Wi-Fi in the central library keeps disconnecting on my laptop.", minutes_ago=1500)
    wifi.status = "IN_PROGRESS"
    eng.audit(db, wifi, wifi.assigned_staff, "STATUS_CHANGE", "ASSIGNED", "IN_PROGRESS", "Investigating access point")
    db.add(RequestMessage(request_id=wifi.id, author_id=wifi.assigned_staff_id, from_staff=True, body="We're checking the library access points. Which floor are you on?"))
    db.add(RequestMessage(request_id=wifi.id, author_id=students[0].id, from_staff=False, body="Second floor, near the reading room."))
    db.add(InternalNote(request_id=wifi.id, author_id=wifi.assigned_staff_id, body="AP-L2-03 firmware outdated; vendor ticket raised. (Staff-only note.)"))
    done = make(students[2], "Hostel mess food quality", "Food quality in the mess has dropped this week, just wanted to give feedback.", minutes_ago=3000)
    done.status, done.resolved_at, done.resolution_note = "RESOLVED", ago(minutes=2000), "Mess committee reviewed the menu and vendor."
    eng.audit(db, done, done.assigned_staff, "STATUS_CHANGE", "ASSIGNED", "RESOLVED", done.resolution_note)
    db.commit()

    total = db.query(CampusSupportRequest).count()
    print(f"Seeded {total} requests, {len(students)} students, {len(STAFF)} staff/authority accounts, {len(DEPTS)} departments.")
    print(f"All demo accounts use password: {DEMO_PASSWORD}")
    db.close()


if __name__ == "__main__":
    run()
