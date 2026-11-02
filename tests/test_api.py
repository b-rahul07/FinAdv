"""API: sign-in, chats with streaming and history, profile versions, feedback, export and delete."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from conftest import MID
from finadvisor.api import runtime as rt_mod
from finadvisor.llm.fake import FakeLLM
from finadvisor.settings import Settings
from test_pipeline import consistent_planner


def fake_news(products, k):
    return {"as_of": "2026-11-01T06:00:00+00:00", "stale": False, "mood": "mixed", "source": "test feed",
            "items": [{"headline": "Markets end flat", "source": "test feed", "url": None,
                       "published": "2026-11-01T05:00:00+00:00", "mood": "neutral", "confidence": 0.9}]}


@pytest.fixture
def client(tmp_path):
    s = Settings(database_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}", auth_mode="dev", app_env="dev",
                 _env_file=None)
    docs = [{"id": "d1", "title": "ELSS", "source": "03_elss.txt",
             "text": "ELSS funds have a 3-year lock-in and qualify for Section 80C up to ₹1.5 lakh."}]
    rt_mod.set_runtime(rt_mod.Runtime(settings=s, llm=FakeLLM(consistent_planner,
                                       text_fn=lambda sy, p, purpose: "ELSS has a 3-year lock-in [1]. It counts for 80C."),
                                       retriever=lambda q, k: docs, news=fake_news))
    from finadvisor.api.app import create_app
    c = TestClient(create_app())
    yield c
    rt_mod.set_runtime(None)


def login(c, email="asha@example.com"):
    tok = c.post("/api/dev/login", json={"email": email, "name": "Asha"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def events(resp):
    out = []
    for block in resp.text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.splitlines() if ": " in l)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


PROFILE = {"take_home_monthly": 50000, "expenses_monthly": 30000, "liquid_savings": 40000, "health_cover": 0,
           "experience": "none", "gl_answers": MID,
           "goals": [{"id": "ret", "name": "Retirement", "kind": "retirement", "target_today": 5000000, "horizon_years": 30}]}


def test_requires_sign_in(client):
    assert client.get("/api/chats").status_code == 401
    assert client.get("/api/chats", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_learn_chat_streams_and_is_saved(client):
    h = login(client)
    chat = client.post("/api/chats", json={}, headers=h).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"text": "What is ELSS?"}, headers=h)
    ev = events(r)
    kinds = [k for k, _ in ev]
    assert kinds[0] == "start" and ("route", {"route": "learn"}) in ev and kinds[-1] == "done"
    assert any(k == "sources" for k in kinds)
    full = client.get(f"/api/chats/{chat['id']}", headers=h).json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert "lock-in" in full["messages"][1]["content"]
    assert full["title"] == "What is ELSS?"


def test_plan_needs_profile_then_works_after_confirmation(client):
    h = login(client)
    chat = client.post("/api/chats", json={}, headers=h).json()
    ev = events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Make me a plan for my money"}, headers=h))
    assert any(k == "card" and d["type"] == "profile" for k, d in ev)
    v = client.put("/api/profile", json={"data": PROFILE}, headers=h).json()
    assert v["version"] == 1 and v["health"]["score"] < 7
    ev = events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Make me a plan for my money"}, headers=h))
    card_types = [d["type"] for k, d in ev if k == "card"]
    assert "plan" in card_types and "health_check" in card_types
    done = ev[-1][1]
    assert done["advice_run_id"]
    why = client.get(f"/api/advice/{done['advice_run_id']}", headers=h).json()
    assert why["why"]["capacity"]["level"] == "low" and why["flags"]["auditor"] is True
    recs = client.get("/api/recommendations", headers=h).json()
    assert {r["action"] for r in recs} >= {"build_emergency_fund", "buy_health_cover"}
    rid = next(r["id"] for r in recs if r["action"] == "build_emergency_fund")
    assert client.patch(f"/api/recommendations/{rid}", json={"status": "done"}, headers=h).json()["ok"]


def test_profile_versions_increment(client):
    h = login(client)
    client.put("/api/profile", json={"data": PROFILE}, headers=h)
    v2 = client.put("/api/profile", json={"data": {**PROFILE, "liquid_savings": 200000}}, headers=h).json()
    assert v2["version"] == 2
    assert client.put("/api/profile", json={"data": {"take_home_monthly": -5}}, headers=h).status_code == 422


def test_chat_list_search_rename_pin_delete(client):
    h = login(client)
    a = client.post("/api/chats", json={"title": "Tax questions"}, headers=h).json()
    b = client.post("/api/chats", json={"title": "Car loan"}, headers=h).json()
    client.patch(f"/api/chats/{b['id']}", json={"pinned": True, "title": "Car loan plan"}, headers=h)
    lst = client.get("/api/chats", headers=h).json()
    assert lst[0]["id"] == b["id"] and lst[0]["title"] == "Car loan plan"
    assert [c["id"] for c in client.get("/api/chats?q=tax", headers=h).json()] == [a["id"]]
    assert client.delete(f"/api/chats/{a['id']}", headers=h).status_code == 204
    assert client.get(f"/api/chats/{a['id']}", headers=h).status_code == 404


def test_other_users_cannot_see_chats(client):
    h1, h2 = login(client, "a@example.com"), login(client, "b@example.com")
    c = client.post("/api/chats", json={}, headers=h1).json()
    assert client.get(f"/api/chats/{c['id']}", headers=h2).status_code == 404


def test_feedback_and_regenerate(client):
    h = login(client)
    chat = client.post("/api/chats", json={}, headers=h).json()
    ev = events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "What is ELSS?"}, headers=h))
    mid = ev[-1][1]["message_id"]
    assert client.post(f"/api/messages/{mid}/feedback", json={"rating": -1, "comment": "too short"}, headers=h).json()["ok"]
    got = client.get(f"/api/chats/{chat['id']}", headers=h).json()["messages"][1]
    assert got["feedback"] == {"rating": -1, "comment": "too short"}
    events(client.post(f"/api/chats/{chat['id']}/regenerate", headers=h))
    msgs = client.get(f"/api/chats/{chat['id']}", headers=h).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["id"] != mid


def test_research_opt_in_controls_analytics_and_export_delete(client):
    from sqlalchemy import func, select
    from finadvisor.db.models import AnalyticsEvent
    h = login(client)
    chat = client.post("/api/chats", json={}, headers=h).json()
    events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "What is ELSS?"}, headers=h))
    with rt_mod.get_runtime().Session() as s:
        assert s.scalar(select(func.count()).select_from(AnalyticsEvent)) == 0
    assert client.put("/api/settings/research", json={"opt_in": True}, headers=h).json()["settings"]["research_opt_in"]
    events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "What is PPF?"}, headers=h))
    with rt_mod.get_runtime().Session() as s:
        assert s.scalar(select(func.count()).select_from(AnalyticsEvent)) >= 1
    exp = client.get("/api/me/export", headers=h).json()
    assert exp["user"]["email"] == "asha@example.com" and len(exp["messages"]) >= 4 and exp["consent_events"]
    assert client.delete("/api/me", headers=h).status_code == 204
    with rt_mod.get_runtime().Session() as s:
        assert s.scalar(select(func.count()).select_from(AnalyticsEvent)) == 0


def test_revoke_all_sessions(client):
    h = login(client)
    assert client.get("/api/me/sessions", headers=h).status_code == 200
    assert client.post("/api/me/sessions/revoke-all", headers=h).status_code == 204
    assert client.get("/api/me", headers=h).status_code == 401


def test_what_if_is_deterministic(client):
    h = login(client)
    client.put("/api/profile", json={"data": PROFILE}, headers=h)
    a = client.post("/api/what-if", json={"new_emi": 15000}, headers=h).json()
    assert a["illustrative"] and a["after"]["monthly_surplus"] == 5000
    assert any("Investing would start" in x or "New priority" in x for x in a["explanations"])


def test_prod_refuses_dev_auth():
    with pytest.raises(RuntimeError):
        Settings(app_env="prod", auth_mode="dev", _env_file=None).check()


def test_new_user_parallel_first_requests(client):
    from concurrent.futures import ThreadPoolExecutor
    h = login(client, "race@example.com")
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda p: client.get(p, headers=h).status_code,
                            ["/api/me", "/api/profile", "/api/recommendations", "/api/chats", "/api/me", "/api/profile"]))
    assert codes == [200] * 6
    assert len(client.get("/api/me/sessions", headers=h).json()) == 1


def test_library_documents_are_readable_by_name_only(client):
    h = login(client)
    docs = client.get("/api/library", headers=h).json()["documents"]
    assert docs and all(d["source"].endswith(".txt") for d in docs)
    one = client.get(f"/api/library/{docs[0]['source']}", headers=h).json()
    assert one["title"] == docs[0]["title"] and len(one["text"]) > 100
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", one["updated"])            # shown as the guide's as-of date
    assert client.get("/api/library/..%2F..%2F.env", headers=h).status_code == 404
    assert client.get("/api/library", headers={}).status_code == 401


def test_keyword_retrieval_handles_short_questions():
    from finadvisor.api.runtime import keyword
    assert keyword("What is ELSS?", 3)[0]["title"].startswith("ELSS")      # one content word is enough
    assert keyword("How does PPF work?", 3)[0]["title"].startswith("PPF")
    assert keyword("what is the meaning of life", 3) == []                  # no match -> honest "not found"
