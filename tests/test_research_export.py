"""Anonymised research export: opted-in users only, pseudonymous, no PII or chat text."""

import json
import sys
from pathlib import Path

from finadvisor.api import runtime as rt_mod
from test_api import PROFILE, client, events, login  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import export_research  # noqa: E402


def test_export_only_opted_in_and_scrubbed(client, tmp_path):
    a, b = login(client, "in@example.com"), login(client, "out@example.com")
    for h in (a, b):
        client.put("/api/profile", json={"data": PROFILE}, headers=h)
        chat = client.post("/api/chats", json={}, headers=h).json()
        ev = events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Make me a plan for my money, my name is Asha"}, headers=h))
        client.post(f"/api/messages/{ev[-1][1]['message_id']}/feedback", json={"rating": -1, "comment": "call me on 9999999999"}, headers=h)
    client.put("/api/settings/research", json={"opt_in": True}, headers=a)
    with rt_mod.get_runtime().Session() as s:
        meta = export_research.export(s, tmp_path, "x" * 32)
    assert meta["users"] == 1
    blob = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.jsonl"))
    for secret in ("in@example.com", "out@example.com", "Asha", "9999999999"):
        assert secret not in blob
    assert json.loads((tmp_path / "advice_runs.jsonl").read_text().splitlines()[0])["user"].startswith("u_")
    assert meta["counts"]["feedback"] == 1 and meta["counts"]["advice_runs"] == 1
    # revoking consent removes the user from the next export
    client.put("/api/settings/research", json={"opt_in": False}, headers=a)
    with rt_mod.get_runtime().Session() as s:
        assert export_research.export(s, tmp_path / "2", "x" * 32)["users"] == 0
