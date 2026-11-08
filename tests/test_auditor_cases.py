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
