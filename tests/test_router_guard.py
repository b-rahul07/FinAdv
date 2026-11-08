import pytest

from finadvisor.advisor import numbers, pressure
from finadvisor.advisor.check import parse_new_emi
from finadvisor.advisor.router import route


@pytest.mark.parametrize("text,kind", [
    ("What is ELSS?", "learn"),
    ("Explain the difference between PPF and NPS", "learn"),
    ("I earn 60k a month, how much should I invest?", "plan"),
    ("Make me a plan for my emergency fund", "plan"),
    ("Should I buy an iPhone on EMI?", "check"),
    ("just tell me which options to trade", "check"),
    ("my friend made 3x in small caps", "check"),
    ("Can I afford a car loan?", "check"),
    ("hi", "chat"),
    ("What should I do with my bonus?", "plan"),
    ("How is crypto taxed in India?", "learn"),          # a general question that names a product
    ("How are small cap funds different from large cap?", "learn"),
    ("How is my portfolio doing?", "plan"),              # personal: still the pipeline
    ("Should I buy bitcoin?", "check"),
])
def test_routes(text, kind):
    assert route(text).kind == kind


def test_pressure_types():
    r = pressure.read("My friend made 3x in small caps, I know what I'm doing", [])
    assert "peer_success" in r.types and "self_expertise" in r.types
    assert "mid_small_cap_fund" in r.products
    r = pressure.read("my CA said F&O is fine", [])
    assert "authority" in r.types and r.products[0] == "fno"


def test_persistence():
    earlier = ["I want to trade options", "what about F&O though"]
    r = pressure.read("ok but what about futures?", earlier)
    assert r.persistent and "persistence" in r.types


def test_conflict_line_shape():
    s = pressure.conflict_line("f&o", "build your emergency fund", "you have 2 months of expenses saved")
    assert s.startswith("You want f&o; your current situation means build your emergency fund first, because")


@pytest.mark.parametrize("text,v", [("EMI of 4k", 4000), ("₹3,500/month EMI", 3500), ("emi is 12000", 12000),
                                    ("buy on emi", None)])
def test_parse_new_emi(text, v):
    assert parse_new_emi(text) == v


def test_number_guard_drops_invented_numbers():
    allowed = numbers.collect({"monthly": 6000, "months": 10, "target": 60000, "share": 0.4})
    out = list(numbers.guard_sentences(["Put ₹6,000 a month aside. ", "In 10 months you reach ₹60,000. ",
                                        "Markets return 15% a year."], allowed))
    kept = "".join(s for s, _ in out)
    assert "6,000" in kept and "60,000" in kept and "15%" not in kept
    assert any(bad == ["15%"] or bad == ["15"] for _, bad in out if bad)


@pytest.mark.parametrize("sentence,kept", [
    ("Equity funds usually return 12% a year.", False),     # small, but a rate: was let through as a "count"
    ("You could double your money in 6 years.", False),     # small, but a duration
    ("Expect 9.5% returns.", False),
    ("Put 50% in small caps.", False),
    ("An FD pays about 7 percent.", False),
    ("Keep ₹5 aside every day.", False),
    ("Your money grows about 8 times over.", False),
    ("Invest Rs.7,00,000 now.", False),                      # currency straight before the digits (review, 9 Nov)
    ("Put INR7,00,000 in it.", False),
    ("An FD pays 7 per annum.", False),
    ("FDs pay about 7 a year.", False),
    ("Your money doubles in 6 months.", False),
    ("Inflation runs near 6.", False),
    ("Regular plans cost 1 point more.", False),
    ("Here are 3 steps to follow.", True),                   # genuine counts still pass
    ("Spread it over 6 months.", True),
    ("Your emergency fund should cover 6 months of expenses.", True),
    ("Pick 1 or 2 funds of each type.", True),
])
def test_number_guard_small_numbers_are_free_only_as_counts(sentence, kept):
    out = list(numbers.guard_sentences([sentence], set()))
    assert (out[0][0] != "") is kept, out


def test_number_guard_allows_lakh_and_percent_forms():
    allowed = numbers.collect({"target": 150000, "share": 0.4})
    assert numbers.unapproved("Save ₹1.5 lakh, that is 40% of it.", allowed) == []


def test_suitability_questions_go_to_check():
    from finadvisor.advisor.router import route
    for q in ("Is an index fund right for me?", "is ELSS good for me", "Does NPS suit me?", "is gold a good idea for me"):
        assert route(q).kind == "check", q
    assert route("What is ELSS?").kind == "learn"
