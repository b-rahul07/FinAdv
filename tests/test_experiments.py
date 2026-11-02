"""The experiment runner uses the website's pipeline, appends JSONL and resumes."""

import json

import yaml

from experiments import run as runner


def test_runner_appends_and_resumes(tmp_path, monkeypatch):
    cfg = {"run_id": "t", "pipeline": "pipeline/default.yaml", "model": "tiny-test",
           "inputs": "experiments/data/smoke_profiles.jsonl", "output": str(tmp_path / "out.jsonl")}
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg))
    runner.main(str(p))
    lines = (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[0])
    for k in ("model", "versions", "flags", "templates", "audit", "final_plan", "run_config_hash"):
        assert k in rec
    runner.main(str(p))   # second run resumes: nothing new
    assert len((tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_runner_refuses_non_synthetic(tmp_path):
    data = tmp_path / "real.jsonl"
    data.write_text(json.dumps({"id": "x", "profile": {"take_home_monthly": 1, "expenses_monthly": 1}}) + "\n")
    cfg = {"run_id": "t", "pipeline": "pipeline/default.yaml", "model": "tiny-test", "inputs": str(data),
           "output": str(tmp_path / "o.jsonl")}
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg))
    try:
        runner.main(str(p))
    except SystemExit as e:
        assert "synthetic" in str(e)
    else:
        raise AssertionError("expected refusal")


def test_replicates_resume_per_replicate(tmp_path):
    cfg = {"run_id": "t", "pipeline": "pipeline/default.yaml", "model": "tiny-test", "replicates": 2,
           "inputs": "experiments/data/smoke_profiles.jsonl", "output": str(tmp_path / "out.jsonl")}
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg))
    runner.main(str(p))
    runner.main(str(p))
    rows = [json.loads(l) for l in (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted((r["profile_id"], r["replicate"]) for r in rows) == sorted(
        (f"smoke-00{i}", k) for i in (1, 2, 3) for k in (0, 1))
