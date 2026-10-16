"""Phase 8 negative and positive cases verification test script."""
import httpx
import json
import uuid
from app.core.database import SessionLocal
from app.models.call_record import CallRecord
from app.models.outreach import Outreach

cases = [
    ("1. interested + valid email", {"email": "user1@example.com", "qualification_outcome": "interested", "next_step_action": "send_info_email"}, "sent", True),
    ("2. meeting requested + valid email", {"email": "user2@example.com", "call_outcome": "MEETING_REQUESTED", "meeting_requested": True}, "sent", True),
    ("3. callback requested + valid email", {"email": "user3@example.com", "call_outcome": "CALLBACK_REQUESTED", "callback_requested": True}, "sent", True),
    ("4. not interested", {"email": "user4@example.com", "qualification_outcome": "not_interested", "next_step_action": "close"}, "skipped", False),
    ("5. wrong person", {"email": "user5@example.com", "qualification_outcome": "wrong_person"}, "skipped", False),
    ("6. do not call", {"email": "user6@example.com", "qualification_outcome": "do_not_call", "next_step_action": "mark_dnc"}, "skipped", False),
    ("7. missing email", {"email": "", "qualification_outcome": "interested"}, "skipped", False),
    ("8. invalid email", {"email": "not-an-email", "qualification_outcome": "interested"}, "skipped", False),
]

org_id = "0d85dc9f-1520-4bcb-8af4-8aad025255cb"
db = SessionLocal()

print("=" * 60)
print("PHASE 8 TEST EXECUTION RESULTS:")
print("=" * 60)

first_cid = None
all_passed = True

for label, vars_dict, expected_status, should_have_email in cases:
    cid = f"call_p8_{uuid.uuid4().hex[:8]}"
    if first_cid is None:
        first_cid = cid
        first_vars = vars_dict

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": cid,
            "agent_id": "agent_3d80320b8eb60bcc212da34856",
            "call_status": "analyzed",
            "duration_ms": 45000,
            "call_analysis": {"custom_analysis_data": vars_dict},
            "metadata": {"organization_id": org_id},
        },
    }
    resp = httpx.post("http://127.0.0.1:8000/api/v1/voice/replay-analyzed-call", json=payload)
    data = resp.json()
    status_match = (data.get("followup_status") == expected_status)
    cr = db.query(CallRecord).filter_by(call_id=cid).first()
    outreaches = db.query(Outreach).filter_by(call_record_id=cr.id).all() if cr else []
    email_match = (len(outreaches) == (1 if should_have_email else 0))
    passed = status_match and email_match
    if not passed:
        all_passed = False
    print(f"[{'PASS' if passed else 'FAIL'}] {label}")
    print(f"       Outcome: followup_status='{data.get('followup_status')}', Outreaches in DB: {len(outreaches)}")

# Case 9: Duplicate webhook check on first call
dup_payload = {
    "event": "call_analyzed",
    "call": {
        "call_id": first_cid,
        "agent_id": "agent_3d80320b8eb60bcc212da34856",
        "call_status": "analyzed",
        "duration_ms": 45000,
        "call_analysis": {"custom_analysis_data": first_vars},
        "metadata": {"organization_id": org_id},
    },
}
r_dup = httpx.post("http://127.0.0.1:8000/api/v1/voice/replay-analyzed-call", json=dup_payload)
data_dup = r_dup.json()
cr_dup = db.query(CallRecord).filter_by(call_id=first_cid).first()
outreaches_dup = db.query(Outreach).filter_by(call_record_id=cr_dup.id).all() if cr_dup else []
dup_passed = (data_dup.get("duplicate") is True) and (len(outreaches_dup) == 1)
if not dup_passed:
    all_passed = False
print(f"[{'PASS' if dup_passed else 'FAIL'}] 9. duplicate webhook -> no duplicate email")
print(f"       Outcome: duplicate={data_dup.get('duplicate')}, Outreaches in DB: {len(outreaches_dup)}")
print("=" * 60)
print(f"FINAL RESULT: {'ALL 9 CASES PASSED PERFECTLY' if all_passed else 'SOME CASES FAILED'}")
print("=" * 60)
