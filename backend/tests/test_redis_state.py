"""Shared-state plumbing: chat store codec/fallback and broker identity."""
from app.services import events as events_mod
from app.services.chat_store import ChatStore, _decode, _encode


def test_chat_store_encode_decode_roundtrip():
    convo = {
        "schedule_run_id": 7,
        "views": {"teacher", "master"},
        "formats": {"pdf", "xlsx"},
        "time_pref": "Morning",
        "asked_time": True,
        "history": [{"user": "hi"}],
        "pending_edit": {"op": "cancel", "course_id": 3},
    }
    back = _decode(_encode(convo))
    assert back["views"] == {"teacher", "master"}   # sets survive the round trip
    assert back["formats"] == {"pdf", "xlsx"}
    assert back["pending_edit"] == {"op": "cancel", "course_id": 3}
    assert back["schedule_run_id"] == 7


def test_decode_fills_defaults_for_missing_keys():
    back = _decode('{"views": [], "formats": []}')
    assert back["views"] == set()
    assert back["pending_edit"] is None
    assert back["asked_time"] is False
    assert back["history"] == []


def test_chat_store_memory_fallback_crud():
    store = ChatStore(client=None)
    assert store.backend == "memory"
    store.set("c1", {"views": {"a"}, "formats": set()})
    got = store.get("c1")
    assert got is not None and got["views"] == {"a"}
    store.delete("c1")
    assert store.get("c1") is None
    store.set("c2", {"x": 1})
    store.clear()
    assert store.get("c2") is None


def test_broker_has_origin_and_reports_backend():
    assert events_mod.broker.origin
    assert events_mod.broker.backend in ("redis", "in-process")


def test_broker_publish_stamps_origin_so_replicas_dont_echo():
    events_mod.reset()
    event = events_mod.broker.publish({"type": "x"})
    assert event["origin"] == events_mod.broker.origin
    assert event["seq"] >= 1
