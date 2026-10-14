"""File upload + table/CSV equivalence tests (shared API client)."""
from tests.shared import get_client
from app.services.planner import build_problem

client = get_client()

CSV_TEXT = """teacher_name,course_name,credit_hours,student_group,preferred_time
Dr. Ahmad Ali,Data Structures,3,CS-2024-A,Morning
Ms. Fatima Khan,Database Systems,4,CS-2024-A,Afternoon
Mr. Hassan Khan,Web Development,3,CS-2024-B,
Bad Row,,9,CS-X,Midnight
Dr. Ahmad Ali,Data Structures,2,CS-2024-A,
"""


def test_upload_csv_validates_rows():
    r = client.post("/upload/file", files={"file": ("data.csv", CSV_TEXT, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_rows"] == 5
    assert len(body["courses"]) == 3
    assert {t["name"] for t in body["teachers"]} == {
        "Dr. Ahmad Ali", "Ms. Fatima Khan", "Mr. Hassan Khan"}
    assert len(body["errors"]) == 2  # bad row + duplicate
    messages = " | ".join(e["message"] for e in body["errors"])
    assert "Credit hours must be 1 to 4" in messages
    assert "Duplicate" in messages
    assert len(body["preview"]) == 3


def test_upload_xlsx_parses():
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws = wb.active
    ws.append(["teacher_name", "course_name", "credit_hours", "student_group", "preferred_time"])
    ws.append(["Alice", "Math", 2, "CS-A", "Morning"])
    ws.append(["Bob", "Art", 1, "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(
        "/upload/file",
        files={"file": ("data.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["courses"]) == 2 and not body["errors"]


def test_upload_rejects_other_extensions():
    r = client.post("/upload/file", files={"file": ("data.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400


def _table_payload():
    return {
        "teachers": [
            {"name": "Dr. Ahmad Ali"},
            {"name": "Ms. Fatima Khan"},
            {"name": "Mr. Hassan Khan"},
        ],
        "courses": [
            {"name": "Data Structures", "teacher": "Dr. Ahmad Ali",
             "credit_hours": 3, "student_group": "CS-2024-A", "preferred_time": "Morning"},
            {"name": "Database Systems", "teacher": "Ms. Fatima Khan",
             "credit_hours": 4, "student_group": "CS-2024-A", "preferred_time": "Afternoon"},
            {"name": "Web Development", "teacher": "Mr. Hassan Khan",
             "credit_hours": 3, "student_group": "CS-2024-B", "preferred_time": ""},
        ],
        "rooms": [],
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "day_start": "09:00",
        "day_end": "17:00",
        "period_minutes": 60,
        "gap_minutes": 30,
        "lunch_break": True,
        "lunch_start": "12:00",
        "lunch_end": "14:00",
    }


def test_table_and_csv_produce_identical_problem():
    """Same data via typed table and via CSV upload -> identical solver input."""
    r = client.post("/upload/file", files={"file": ("data.csv", CSV_TEXT, "text/csv")})
    assert r.status_code == 200
    uploaded = r.json()
    csv_problem = build_problem({
        **_table_payload(),
        "teachers": uploaded["teachers"],
        "courses": uploaded["courses"],
    })
    table_problem = build_problem(_table_payload())
    for key in ("faculty", "venues", "slots", "courses", "session_groups"):
        assert csv_problem[key] == table_problem[key], key
    assert csv_problem["summary"]["student_groups"] == ["CS-2024-A", "CS-2024-B"]
