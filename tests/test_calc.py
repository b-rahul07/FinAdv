"""Calculators: hand-checked values plus independent month-by-month simulations."""

from datetime import date

import pytest

from finadvisor.calc import deposits, goals, loans, money, tax, xirr
from finadvisor.configs import default_bundle


# ---- money formatting
@pytest.mark.parametrize("n,s", [(0, "0"), (100, "100"), (1000, "1,000"), (100000, "1,00,000"),
                                 (12345678, "1,23,45,678"), (-1500000, "-15,00,000")])
def test_group_indian(n, s):
    assert money.group_indian(n) == s


def test_inr():
    assert money.inr(1234567.5, 2) == "₹12,34,567.50"
    assert money.inr(5999.5) == "₹6,000"
    assert money.inr_words(1250000) == "₹12.5 lakh"
    assert money.inr_words(32000000) == "₹3.2 crore"


def test_round_up_to():
    assert money.round_up_to(5833.33, 100) == 5900
    assert money.round_up_to(6000, 100) == 6000


# ---- XIRR
def test_xirr_one_year_leap():
    # 2020 is a leap year: 366 days. 1000 * (1 + r)^(366/365) = 1100.
    r = xirr.xirr([(date(2020, 1, 1), -1000), (date(2021, 1, 1), 1100)])
    assert r == pytest.approx(1.1 ** (365 / 366) - 1, abs=1e-9)


def test_xirr_monthly_sip_matches_definition():
    flows = [(date(2024, m, 1), -10_000) for m in range(1, 13)] + [(date(2025, 1, 1), 130_000)]
    r = xirr.xirr(flows)
    t0 = flows[0][0]
    npv = sum(cf / (1 + r) ** ((d - t0).days / 365) for d, cf in flows)
    assert abs(npv) < 1e-6
    assert 0.15 < r < 0.17


def test_xirr_undefined_cases():
    assert xirr.xirr([(date(2024, 1, 1), -1000)]) is None
    assert xirr.xirr([(date(2024, 1, 1), -1000), (date(2024, 6, 1), -1000)]) is None


def test_xirr_loss():
    r = xirr.xirr([(date(2023, 1, 1), -1000), (date(2024, 1, 1), 800)])
    assert r == pytest.approx(-0.2, abs=1e-9)


def test_short_period_not_annualised():
    assert not xirr.is_annualisable(date(2026, 1, 1), date(2026, 12, 31))
    assert xirr.is_annualisable(date(2025, 1, 1), date(2026, 1, 1))


# ---- goals and SIPs
def _simulate_sip(monthly, annual_pct, months):
    i = goals.monthly_rate(annual_pct)
    bal = 0.0
    for _ in range(months):
        bal = (bal + monthly) * (1 + i)
    return bal


def test_fv_sip_matches_simulation():
    assert goals.fv_sip(5000, 12, 120) == pytest.approx(_simulate_sip(5000, 12, 120), rel=1e-12)


def test_sip_needed_round_trip():
    s = goals.sip_needed(1_000_000, 12, 60)
    assert _simulate_sip(s, 12, 60) == pytest.approx(1_000_000, rel=1e-9)
    assert s == pytest.approx(12_330, abs=5)  # hand check: 10 lakh / 81.10 ≈ 12,330


def test_sip_needed_counts_existing_savings():
    s = goals.sip_needed(1_000_000, 10, 60, already_saved=1_000_000)
    assert s == 0.0


def test_inflate():
    assert goals.inflate(100_000, 6, 10) == pytest.approx(179_084.77, abs=0.01)


def test_months_to_save():
    assert goals.months_to_save(60_000, 6_000) == 10
    assert goals.months_to_save(60_001, 6_000) == 11
    assert goals.months_to_save(0, 6_000) == 0


# ---- loans
def test_emi_known_value():
    # ₹10 lakh at 8.5% for 20 years: ₹8,678.23 (standard bank calculators)
    assert loans.emi(1_000_000, 8.5, 240) == pytest.approx(8678.23, abs=0.01)


def test_months_to_repay_round_trip():
    e = loans.emi(500_000, 12, 36)
    assert loans.months_to_repay(500_000, 12, e) == 36
    assert loans.months_to_repay(500_000, 12, 5000) is None   # interest alone is 5000


# ---- deposits
def test_fd_quarterly_one_year():
    v = deposits.fd_value(100_000, 7, date(2025, 1, 1), date(2026, 1, 1), date(2027, 1, 1))
    assert v == pytest.approx(100_000 * 1.0175 ** 4, rel=1e-12)
    assert round(v, 2) == 107185.90


def test_fd_capped_at_maturity():
    a = deposits.fd_value(100_000, 7, date(2025, 1, 1), date(2030, 1, 1), date(2026, 1, 1))
    b = deposits.fd_value(100_000, 7, date(2025, 1, 1), date(2026, 1, 1), date(2026, 1, 1))
    assert a == b


def test_rd_value_no_interest_equals_sum():
    v = deposits.rd_value(1000, 0, date(2025, 1, 1), date(2026, 1, 1), date(2026, 1, 1))
    assert v == pytest.approx(12_000)
    assert deposits.rd_instalments_paid(date(2025, 1, 1), date(2025, 3, 15), date(2026, 1, 1)) == 3


# ---- tax
def test_long_term_needs_more_than_12_months():
    cfg = default_bundle().tax
    assert not tax.is_long_term_equity(date(2025, 10, 31), date(2026, 10, 31), cfg)
    assert tax.is_long_term_equity(date(2025, 10, 31), date(2026, 11, 1), cfg)


def test_ltcg_estimate():
    cfg = default_bundle().tax
    t = tax.equity_tax_estimate(200_000, 10_000, cfg)
    assert t["taxable_ltcg"] == 75_000
    assert t["ltcg_tax"] == pytest.approx(9_375)
    assert t["stcg_tax"] == pytest.approx(2_000)
