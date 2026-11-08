"""The document library: every guide is well-formed, dated and sourced, and is split into labelled sections."""

import re

from finadvisor.retrieval import DOCS_DIR
from finadvisor.retrieval.chunks import MAX_CHARS, chunk_text, doc_title, last_checked, parse

GUIDES = sorted(DOCS_DIR.glob("*.txt"))


def test_every_guide_has_a_title_date_sections_and_sources():
    assert len(GUIDES) >= 40
    for f in GUIDES:
        text = f.read_text(encoding="utf-8")
        title, checked, sections = parse(text)
        assert title and len(title) <= 120, f.name
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked or ""), f"{f.name}: no 'Last checked: YYYY-MM-DD' line"
        assert len(sections) >= 3, f.name
        assert "\nSources\n" in text and "https://" in text.split("\nSources\n")[1], f"{f.name}: no sources"


def test_guides_use_current_tax_law_names():
    for f in GUIDES:
        text = f.read_text(encoding="utf-8")
        if re.search(r"\b80C\b|\b80D\b|\b80E\b", text):
            # old numbers only next to the new ones ("section 123 (formerly 80C)")
            assert re.search(r"section 12[3-9]|formerly", text, re.I), f"{f.name} cites old section numbers alone"


def test_sections_become_labelled_pieces_without_sources():
    text = ("Health Insurance\nLast checked: 2026-11-08\n\nWhy you need it\nBills are big.\n\n"
            "What to check\n- Room rent limits\n- Waiting periods\n\nSources\n- IRDAI: https://irdai.gov.in/\n")
    pieces = chunk_text("x.txt", text)
    assert [p.content.split("\n")[0] for p in pieces] == ["Health Insurance — Why you need it",
                                                          "Health Insurance — What to check"]
    assert "Room rent limits" in pieces[1].content
    assert not any("irdai.gov.in" in p.content or "Last checked" in p.content for p in pieces)
    assert pieces[0].chunk_id == "x.txt_chunk0"


def test_long_sections_are_split_and_every_piece_keeps_its_label():
    body = " ".join(f"Sentence number {i} explains something useful." for i in range(80))
    pieces = chunk_text("y.txt", f"Guide\nLast checked: 2026-11-08\n\nA long section\n{body}\n")
    assert len(pieces) > 1
    assert all(p.content.startswith("Guide — A long section\n") for p in pieces)
    assert all(len(p.content) <= MAX_CHARS + 60 for p in pieces)


def test_titles_and_dates_come_from_the_guide():
    assert doc_title("01_tax_saving_deductions.txt").startswith("Tax-Saving Deductions")
    assert last_checked("01_tax_saving_deductions.txt") == "2026-11-08"
    assert doc_title("99_no_such_guide.txt") == "No Such Guide"


def test_keyword_search_finds_new_topics():
    from finadvisor.api.runtime import keyword
    for q, want in [("old regime or new regime which is better", "16_income_tax_regimes.txt"),
                    ("how to improve my cibil credit score", "26_credit_score.txt"),
                    ("someone promised guaranteed returns on telegram", "34_avoiding_financial_scams.txt")]:
        assert want in [d["source"] for d in keyword(q, 3)], q
