"""Constraint validation tests."""
import pytest
from app.services.validator import ValidationError, validate_generate_request
from tests.conftest import make_small_instance


def _payload():
    faculty, venues, slots, courses = make_small_instance()
    return {"faculty": faculty, "venues": venues, "slots": slots, "courses": courses}


def test_valid_payload_passes():
    validate_generate_request(_payload())


def test_unknown_faculty_rejected():
    p = _payload()
    p["courses"][0]["faculty_id"] = 999
    with pytest.raises(ValidationError, match="unknown faculty"):
        validate_generate_request(p)


def test_zero_capacity_venue_rejected():
    p = _payload()
    p["venues"][0]["capacity"] = 0
    with pytest.raises(ValidationError):
        validate_generate_request(p)


def test_no_capable_venue_rejected():
    p = _payload()
    p["courses"][0]["capacity_required"] = 10_000
    with pytest.raises(ValidationError, match="no venue satisfies"):
        validate_generate_request(p)


def test_bad_slot_time_rejected():
    p = _payload()
    p["slots"][0]["end_time"] = "08:00"  # before start 09:00
    with pytest.raises(ValidationError, match="end must be after start"):
        validate_generate_request(p)


def test_empty_lists_rejected():
    p = _payload()
    p["courses"] = []
    with pytest.raises(ValidationError):
        validate_generate_request(p)
