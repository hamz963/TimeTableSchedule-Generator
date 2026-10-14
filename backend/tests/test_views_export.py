"""Multi-view + multi-format export tests (shared API client)."""
import pytest
from tests.shared import get_client

client = get_client()

FORMATS = ["csv", "xlsx", "pdf", "png", "jpg", "json", "html"]
VIEWS = ["master", "teacher", "student", "staff", "canteen"]


def _run_id():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 2},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue"],
        "day_start": "08:00",
        "day_end": "12:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["schedule_run_id"]


def test_all_views_return_expected_shapes():
    run_id = _run_id()
    assert (await_view("master", run_id))["headers"][0] == "Time"
    teacher = await_view("teacher", run_id)
    assert {t["name"] for t in teacher["teachers"]} == {"Alice", "Bob"}
    student = await_view("student", run_id)
    assert len(student["courses"]) == 2
    staff = await_view("staff", run_id)
    assert staff["slots"] and "concurrent_classes" in staff["slots"][0]
    canteen = await_view("canteen", run_id)
    assert canteen["peak_slots"] and "slots" in canteen


def await_view(view, run_id):
    r = client.get(f"/schedule/{run_id}/views", params={"view": view})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["view"] == view
    return body


def test_views_reject_bad_input():
    run_id = _run_id()
    assert client.get(f"/schedule/{run_id}/views", params={"view": "nope"}).status_code == 400
    assert client.get("/schedule/999999/views").status_code == 404


@pytest.mark.parametrize("fmt", FORMATS)
def test_all_formats_export(fmt):
    run_id = _run_id()
    r = client.get(f"/export/{run_id}", params={"view": "master", "format": fmt})
    assert r.status_code == 200, r.text
    assert len(r.content) > 50


def test_export_magic_bytes():
    run_id = _run_id()
    pdf = client.get(f"/export/{run_id}", params={"format": "pdf"}).content
    assert pdf.startswith(b"%PDF")
    png = client.get(f"/export/{run_id}", params={"format": "png"}).content
    assert png.startswith(b"\x89PNG")
    jpg = client.get(f"/export/{run_id}", params={"format": "jpg"}).content
    assert jpg.startswith(b"\xff\xd8")
    xlsx = client.get(f"/export/{run_id}", params={"format": "xlsx"}).content
    assert xlsx.startswith(b"PK")
    html = client.get(f"/export/{run_id}", params={"format": "html"}).content
    assert b"<!DOCTYPE html>" in html
    data = client.get(f"/export/{run_id}", params={"format": "json"}).json()
    assert data["view"] == "master" and "metrics" in data


def test_export_rejects_bad_input():
    run_id = _run_id()
    assert client.get(f"/export/{run_id}", params={"format": "docx"}).status_code == 400
    assert client.get(f"/export/{run_id}", params={"view": "nope"}).status_code == 400
    assert client.get("/export/999999").status_code == 404


def test_each_view_exports_to_pdf():
    run_id = _run_id()
    for view in VIEWS:
        r = client.get(f"/export/{run_id}", params={"view": view, "format": "pdf"})
        assert r.status_code == 200 and r.content.startswith(b"%PDF"), view
