"""Shared test fixtures: small deterministic problem instance."""
import pytest


def make_small_instance():
    slots = [
        {"id": 1, "day_of_week": "Mon", "start_time": "09:00", "end_time": "10:00", "duration_minutes": 60},
        {"id": 2, "day_of_week": "Mon", "start_time": "10:00", "end_time": "11:00", "duration_minutes": 60},
        {"id": 3, "day_of_week": "Tue", "start_time": "09:00", "end_time": "10:00", "duration_minutes": 60},
    ]
    faculty = [
        {"id": 1, "name": "Alice", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [1], "unavailable_slots": [3]},
        {"id": 2, "name": "Bob", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [], "unavailable_slots": []},
    ]
    venues = [
        {"id": 1, "name": "R101", "capacity": 50, "equipment": ["projector"], "available_slots": []},
        {"id": 2, "name": "R102", "capacity": 30, "equipment": [], "available_slots": []},
    ]
    courses = [
        {"id": 1, "name": "Math", "code": "M101", "faculty_id": 1, "capacity_required": 40,
         "duration_minutes": 60, "required_equipment": ["projector"]},
        {"id": 2, "name": "Physics", "code": "P101", "faculty_id": 1, "capacity_required": 20,
         "duration_minutes": 60, "required_equipment": []},
        {"id": 3, "name": "Chem", "code": "C101", "faculty_id": 2, "capacity_required": 25,
         "duration_minutes": 60, "required_equipment": []},
    ]
    return faculty, venues, slots, courses


@pytest.fixture
def small_instance():
    return make_small_instance()
