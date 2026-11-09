"""Every twin check says what could make it fail (trivial / gate_decides / tests_llm / no_model); pass/fail unchanged."""

from finadvisor.advisor import auditor
from finadvisor.advisor.core import plan_once
from finadvisor.llm.fake import FakeLLM
from test_pipeline import consistent_planner


def _checks(bundle, profile, **pipeline):
    b = bundle.with_pipeline({**bundle.pipeline, **pipeline,
                              "auditor": {**bundle.pipeline["auditor"], "early_exit": False, "time_budget_s": None}})
    llm = FakeLLM(consistent_planner)
    return auditor.audit(plan_once(profile, b, llm), b, llm).attempts[0].checks


def test_every_check_has_a_case(bundle, healthy, stretched):
    for p in (healthy, stretched):
        checks = _checks(bundle, p)
        assert checks and all(c.case in auditor.CASES for c in checks)
        assert all(c.case == "trivial" for c in checks if c.trivial)
        assert all(c.case == "tests_llm" for c in checks if c.relation == "MR6")


def test_low_capacity_twins_are_trivial_and_mr5_never_gate_decides(bundle, healthy, stretched):
    for p in (healthy, stretched):
        for c in _checks(bundle, p):
            if c.relation == "MR5":
                assert c.case in ("trivial", "tests_llm")


def test_gate_off_leaves_no_trivial_or_gate_decided_checks(bundle, healthy):
    stages = {**bundle.pipeline["stages"], "gate": False}
    checks = _checks(bundle, healthy, stages=stages)
    assert {c.case for c in checks} == {"tests_llm"}


def test_standard_mix_tests_no_model(bundle, healthy):
    planner = {**bundle.pipeline.get("planner", {}), "mode": "standard"}
    checks = _checks(bundle, healthy, planner=planner)
    assert {c.case for c in checks} <= {"trivial", "no_model"}
    assert any(c.case == "no_model" for c in checks)


def test_healthy_profile_has_checks_that_test_the_model(bundle, healthy):
    # High capacity and willingness: twins keep risky products, so the model's choice is what is tested
    assert any(c.case == "tests_llm" for c in _checks(bundle, healthy) if c.relation != "MR6")


def _mr6(bundle, profile, compare, planner):
    twins = {**bundle.pipeline["auditor"]["twins"], "MR6_compare": compare}
    b = bundle.with_pipeline({**bundle.pipeline, "auditor": {**bundle.pipeline["auditor"], "twins": twins,
                                                             "early_exit": False, "time_budget_s": None}})
    llm = FakeLLM(planner)
    return [c.holds for c in auditor.audit(plan_once(profile, b, llm), b, llm).attempts[0].checks
            if c.relation == "MR6"]


def wording_sensitive(risky_when_casual: bool):
    """Plain wording: the two safest products 6:4. Casual: the three safest 4:3:3, or the riskiest if asked."""
    from test_pipeline import RISK, allowed_by_bucket

    def fn(system, prompt, schema, purpose):
        if not purpose.startswith("planner"):
            return {}
        out = {}
        for bid, items in allowed_by_bucket(prompt).items():
            safe = sorted(items, key=lambda x: (RISK.index(x[1]), x[0]))
            if purpose.endswith("casual"):
                pick = sorted(items, key=lambda x: -RISK.index(x[1]))[:1] if risky_when_casual else safe[:3]
                out[bid] = ",".join(f"{p}:{w}" for (p, _), w in zip(pick, (4, 3, 3)))
            else:
                out[bid] = ",".join(f"{p}:{w}" for (p, _), w in zip(safe[:2], (6, 4)))
        return out
    return fn


def test_mr6_risk_variant_ignores_splits_among_same_risk_products(bundle, stretched, healthy):
    """Smoke pass, 9 Nov: most fallbacks were MR6 failures where wording only changed the split among low-risk
    products. 'shares' (pipeline-v4) fails them; 'risk' (pipeline-v4-mr6risk, sensitivity run S2) does not, but
    still fails a wording change that moves money into risky products."""
    same_risk = wording_sensitive(risky_when_casual=False)
    assert _mr6(bundle, stretched, "shares", same_risk)[0] is False
    assert _mr6(bundle, stretched, "risk", same_risk)[0] is True
    riskier = wording_sensitive(risky_when_casual=True)
    assert _mr6(bundle, healthy, "risk", riskier)[0] is False


def test_mr6_risk_pipeline_file_differs_only_in_the_comparison():
    import yaml
    from finadvisor.configs import CONFIG_DIR
    a = yaml.safe_load((CONFIG_DIR / "pipeline/default.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((CONFIG_DIR / "pipeline/pipeline-v4-mr6risk.yaml").read_text(encoding="utf-8"))
    assert b["version"] == "pipeline-v4-mr6risk" and b["auditor"]["twins"].pop("MR6_compare") == "risk"
    b["version"] = a["version"]
    assert a == b
