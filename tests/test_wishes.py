"""Answer-first framing (wish-v1) and the "What I looked at" evidence card."""

import json
import time

from finadvisor.advisor.pipeline import NEWS_NOTE, Advisor
from finadvisor.llm.fake import FakeLLM
from finadvisor.market.news import NewsDesk, overall
from test_pipeline import consistent_planner, run_turn

DOCS = [{"id": "d1", "title": "SIP Systematic Investment Plan", "source": "04_sip.txt",
         "text": "A SIP invests a fixed amount every month into a mutual fund. Index funds track the Nifty 50 from ₹4,321 a month."},
        {"id": "d2", "title": "SIP Systematic Investment Plan", "source": "04_sip.txt", "text": "Same document, second chunk."},
        {"id": "d3", "title": "SEBI Mutual Fund Regulations", "source": "07_sebi.txt", "text": "Riskometer levels."}]
NEWS = {"as_of": "2026-11-01T06:00:00+00:00", "stale": False, "mood": "positive", "source": "test feed",
        "items": [{"headline": "Nifty hits record high on FII buying", "source": "test feed", "url": None,
                   "published": None, "mood": "positive", "confidence": 0.93}]}


def advisor(text="Here is how the steps fit together.", seen=None):
    def text_fn(system, prompt, purpose):
        if seen is not None:
            seen.append(prompt)
        return text
    return Advisor(_bundle(), FakeLLM(consistent_planner, text_fn=text_fn),
                   retriever=lambda q, k: DOCS, news=lambda products, k: NEWS)


def _bundle():
    from conftest import model_bundle
    return model_bundle()


def test_stock_question_answers_first_then_strong_advice(stretched):
    out, _ = run_turn(advisor(), stretched, "what stocks should I invest in")
    assert out.text.startswith("I can't name individual stocks.")
    assert "Nifty 50 index fund" in out.text
    first, advice = out.text.split("\n\n")[:2]
    assert advice.startswith("**My advice:** I strongly advise you to build your emergency fund")
    assert out.advice["wish"]["severity"] == "strong"
    assert out.advice["check"]["conflict"].startswith("You want direct shares;")   # Algorithm 3 line still recorded


def test_stock_question_for_healthy_profile_is_a_suggestion(healthy):
    out, _ = run_turn(advisor(), healthy, "which stocks should i buy")
    assert out.advice["wish"]["severity"] == "suggest"
    assert "**My advice:** I'd suggest" in out.text
    assert "strongly" not in out.text


def test_small_cap_fits_but_needs_a_long_goal(healthy):
    healthy.goals = []
    out, _ = run_turn(advisor(), healthy, "My friend made 3x in small caps, just put my money in small caps")
    assert out.route == "plan"
    assert "not in your plan today" in out.text
    assert "let the plan set the amount, not the rally" in out.text     # peer-success pressure gets the nudge


PUSH = "My friend made 3x in small caps, just put my money in small caps"   # Plan route (pressure)


def test_evidence_card_lists_documents_and_headlines(stretched):
    seen: list[str] = []
    out, _ = run_turn(advisor(seen=seen), stretched, PUSH)
    ev = next(c for c in out.cards if c["type"] == "evidence")
    assert [d["source"] for d in ev["documents"]] == ["04_sip.txt", "07_sebi.txt"]    # one passage per document
    assert ev["news"]["items"][0]["mood"] == "positive" and ev["news"]["note"] == NEWS_NOTE
    assert out.advice["evidence"] == ev
    explain = seen[-1]
    # default: passages are shown to the person but not given to the model; news never reaches the model
    assert "BACKGROUND" not in explain and "Nifty hits record high" not in explain
    assert out.advice["templates"]["wish"].startswith("wish-v1@")
    adv = advisor(seen=seen)
    adv.bundle.pipeline["evidence"] = {**adv.bundle.pipeline["evidence"], "documents_in_prompt": True}
    run_turn(adv, stretched, PUSH)
    assert "BACKGROUND" in seen[-1] and "Nifty hits record high" not in seen[-1]


def test_check_answers_have_no_model_prose(stretched):
    out, _ = run_turn(advisor(text="We can explore stocks later."), stretched, "what stocks should I invest in")
    assert "explore" not in out.text
    assert any(c["type"] == "evidence" for c in out.cards)
    assert not [g for g in out.generations if g.purpose == "explain"]


def test_numbers_from_documents_are_not_approved(stretched):
    out, _ = run_turn(advisor(text="Index funds start from ₹4,321 a month. They are simple."), stretched, PUSH)
    assert "4,321" not in out.text and "They are simple." in out.text


def test_promises_of_later_suitability_are_dropped(stretched):
    out, _ = run_turn(advisor(text="Once you have this fund in place, we can explore small caps. Safety comes first."),
                      stretched, PUSH)
    assert "explore small caps" not in out.text and "Safety comes first." in out.text


def test_evidence_can_be_switched_off(stretched):
    adv = advisor()
    adv.bundle.pipeline["evidence"] = {"documents": 0, "headlines": 0}
    out, _ = run_turn(adv, stretched, "what stocks should I invest in")
    assert not any(c["type"] == "evidence" for c in out.cards)


# ---------------------------------------------------------------- news desk

def test_news_desk_caches_and_filters_by_topic(tmp_path):
    calls = []

    def fetcher():
        calls.append(1)
        return [{"headline": "Sensex slips 300 points", "source": "A", "url": None, "published": None},
                {"headline": "Gold prices rise on safe-haven demand", "source": "B", "url": None, "published": None},
                {"headline": "RBI keeps repo rate unchanged", "source": "A", "url": None, "published": None}]

    def classifier(items):
        moods = {"Sensex": ("negative", 0.9), "Gold": ("positive", 0.8), "RBI": ("neutral", 0.7)}
        return [{**h, "mood": moods[h["headline"].split()[0]][0], "confidence": moods[h["headline"].split()[0]][1]}
                for h in items]

    desk = NewsDesk(path=tmp_path / "news.json", fetcher=fetcher, classifier=classifier)
    empty = desk.get(["gold_etf_fund"])          # nothing cached yet: returns at once, refreshes in the background
    assert empty["items"] == [] and empty["as_of"] is None
    for _ in range(50):
        if (tmp_path / "news.json").exists():
            break
        time.sleep(0.05)
    got = NewsDesk(path=tmp_path / "news.json", fetcher=fetcher, classifier=classifier).get(["gold_etf_fund"], k=2)
    assert got["items"][0]["headline"].startswith("Gold")       # topic match first, then general news
    assert len(got["items"]) == 2 and calls == [1]
    assert json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))["model"] == "ProsusAI/finbert"


def test_overall_mood():
    assert overall([{"mood": "positive", "confidence": 0.9}, {"mood": "negative", "confidence": 0.8}]) == "mixed"
    assert overall([{"mood": "negative", "confidence": 0.9}]) == "negative"
    assert overall([{"mood": None, "confidence": None}]) is None


def test_long_goal_but_not_in_plan_is_not_called_missing_goal(healthy, bundle):
    from finadvisor.advisor import check as check_mod, wishes
    from finadvisor.advisor.capacity import assess
    from finadvisor.advisor.gate import gate
    card = check_mod.check(healthy, bundle, ["mid_small_cap_fund"], "small caps")
    cap = assess(healthy, bundle.rules)
    dec = {d.id: d for d in gate(card["suitability"], cap.rule_ids, healthy, bundle.shelf, bundle.rules)}
    w = wishes.frame(card, dec, cap.rule_ids, bundle, in_plan=["large_cap_index_fund"], goal_years=[8])
    assert "no goal that far off" not in w["answer"] and "other diversified funds" in w["answer"]
    w = wishes.frame(card, dec, cap.rule_ids, bundle, in_plan=["large_cap_index_fund"], goal_years=[2])
    assert "no goal that far off" in w["answer"]


def test_which_mutual_funds_names_the_fund_categories_in_the_plan(stretched):
    out, _ = run_turn(advisor(), stretched, "which mutual funds should I invest in")
    assert out.route == "plan"
    assert out.text.startswith("For your risk level, these fund types fit: liquid fund (")
    assert "not specific schemes or fund houses" in out.text and "**What to do**" in out.text


def test_learn_numbers_one_source_per_document():
    chunks = [{"id": f"e#{i}", "title": "ELSS", "source": "03_elss.txt", "text": f"ELSS part {i}."} for i in range(3)] + \
             [{"id": "c#0", "title": "80C", "source": "01_80c.txt", "text": "Section 80C."}]
    seen: list[str] = []
    adv = Advisor(_bundle(), FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: seen.append(p) or "ELSS [1]."),
                  retriever=lambda q, k: chunks)
    out, _ = run_turn(adv, None, "What is ELSS?")
    assert [s["n"] for s in out.sources] == [1, 2] and [s["source"] for s in out.sources] == ["03_elss.txt", "01_80c.txt"]
    assert "[1] ELSS" in seen[-1] and "[2] 80C" in seen[-1] and "[3]" not in seen[-1]


def test_explanation_cannot_name_products_outside_the_plan(stretched):
    text = ("First, get health cover. Once you have an emergency fund, start investing in a balanced advantage fund "
            "or a Flexi-cap fund. Keep the rest in a liquid fund.")
    out, _ = run_turn(advisor(text=text), stretched, "Make me a plan for my savings")
    model_part = out.text.split("\n\n")[-1]
    assert "Flexi-cap" not in model_part and "First, get health cover." in model_part


def test_prompt_jargon_does_not_reach_the_person(stretched):
    out, _ = run_turn(advisor(text="Here is a plan based on the PLAN FACTS: get health cover first."), stretched,
                      "Make me a plan for my savings")
    assert "PLAN FACTS" not in out.text and "based on your plan" in out.text


def test_number_free_explainer_gets_steps_in_words(stretched):
    seen: list[str] = []
    text = "Then, after that, get health cover. Build the fund with ₹10,000. Then keep going."
    out, _ = run_turn(advisor(text=text, seen=seen), stretched, "Make me a plan for my savings")
    prompt = seen[-1]
    facts = prompt.split("PLAN FACTS")[1].split("ALREADY TOLD")[0]
    assert "₹" not in facts and "First: Get health insurance cover" in facts
    model_part = out.text.split("\n\n")[-1].strip()
    # leading connectors are tidied at the start and after a dropped sentence
    assert model_part == "Get health cover. Keep going."


def test_blocked_wish_product_cannot_be_promised(stretched):
    out, _ = run_turn(advisor(text="Build your fund. After that, we'll start investing in mid- and small-cap funds."),
                      stretched, PUSH)
    assert "start investing in mid" not in out.text.split("\n\n")[-1]
