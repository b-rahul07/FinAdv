"""Income tax under both regimes, against figures worked by hand from the FY 2026-27 slabs."""

import pytest

from finadvisor.calc import goals, income_tax


def test_new_regime_worked_examples():
    c = income_tax.compare(1_500_000)
    new = c["new"]
    # 15,00,000 - 75,000 = 14,25,000; 5% of 4L + 10% of 4L + 15% of 2.25L = 20,000 + 40,000 + 33,750; 4% cess
    assert (new["taxable"], new["tax_before_rebate"], new["rebate"]) == (1_425_000, 93_750, 0)
    assert new["total"] == pytest.approx(97_500)
    assert new["marginal_rate"] == pytest.approx(0.15 * 1.04)
    # taxable income of exactly 12 lakh: the rebate wipes the tax out
    assert income_tax.compare(1_275_000)["new"]["total"] == 0
    assert income_tax.compare(1_275_000)["new"]["marginal_rate"] == 0
    # 10,000 above the limit: marginal relief caps the tax at the 10,000 of extra income, plus cess
    just_over = income_tax.compare(1_285_000)["new"]
    assert just_over["tax_before_rebate"] == pytest.approx(61_500) and just_over["total"] == pytest.approx(10_400)


def test_old_regime_deductions_are_capped_and_the_cheaper_regime_is_named():
    c = income_tax.compare(1_500_000, {"deductions_80c": 200_000, "deductions_80d": 25_000})
    old = c["old"]
    assert old["deductions"]["deductions_80c"] == 150_000                 # capped at 1.5 lakh
    # 15,00,000 - 50,000 - 1,75,000 = 12,75,000; 12,500 + 1,00,000 + 30% of 2.75L = 1,95,000; cess 7,800
    assert old["taxable"] == 1_275_000 and old["total"] == pytest.approx(202_800)
    assert c["better"] == "new" and c["saving"] == pytest.approx(202_800 - 97_500)
    assert c["new"]["deductions"] == {}                                   # the new regime takes none of them
    small = income_tax.compare(600_000)
    assert small["old"]["total"] == pytest.approx(23_400) and small["new"]["total"] == 0
    assert income_tax.compare(550_000)["old"]["total"] == 0               # taxable 5 lakh: full rebate, no marginal relief
    assert income_tax.compare(560_000)["old"]["total"] == pytest.approx((12_500 + 2_000) * 1.04)
    assert income_tax.compare(0)["better"] == "same"


def test_surcharge_and_slab_helpers():
    rich = income_tax.compare(6_000_000)["new"]
    assert rich["surcharge"] == pytest.approx(rich["tax_before_rebate"] * 0.10)
    assert income_tax.slab_tax(400_000, income_tax.rules()["new"]["slabs"]) == 0
    assert income_tax.slab_rate(400_000, income_tax.rules()["new"]["slabs"]) == 0.05    # the next rupee


def test_what_filling_80c_and_nps_would_save():
    x = income_tax.with_full_deductions(1_500_000, {"deductions_80c": 50_000})
    assert x["extra_invested"] == 100_000 + 50_000
    # old regime: taxable falls from 14,00,000 to 12,50,000, all in the 30% slab; 1,50,000 x 30% x 1.04
    assert x["old_saving"] == pytest.approx(150_000 * 0.30 * 1.04)
    assert x["new_tax"] == pytest.approx(97_500) and x["better_after"] == "new"
    assert income_tax.with_full_deductions(1_500_000, {"deductions_80c": 150_000, "nps_80ccd1b": 50_000})["extra_invested"] == 0
    assert income_tax.room({"deductions_80c": 50_000})["deductions_80c"] == 100_000


def test_fd_against_debt_fund_after_tax():
    r = income_tax.fd_vs_debt_fund(100_000, 3, 6.5, 6.8, 0.312)
    assert r["fd_after_tax"] == pytest.approx(100_000 * (1 + 0.065 * 0.688) ** 3)
    grown = 100_000 * 1.068 ** 3
    assert r["debt_fund_after_tax"] == pytest.approx(grown - (grown - 100_000) * 0.312)
    assert r["difference"] > 0
    untaxed = income_tax.fd_vs_debt_fund(100_000, 3, 6.5, 6.5, 0.0)
    assert untaxed["difference"] == pytest.approx(0)                     # same rate, no tax: no difference


def test_retirement_corpus_lasts_exactly_the_years_it_is_sized_for():
    corpus = goals.retirement_corpus_today(50_000, 25, 7.0, 6.0)
    # month by month in today's rupees: pay at the start of the month, the rest grows at the real rate
    real_monthly = ((1.07 / 1.06) ** (1 / 12)) - 1
    left = corpus
    for _ in range(25 * 12):
        left = (left - 50_000) * (1 + real_monthly)
    assert abs(left) < 1 and 13_000_000 < corpus < 15_000_000
    assert goals.retirement_corpus_today(50_000, 25, 6.0, 6.0) == pytest.approx(50_000 * 300)
