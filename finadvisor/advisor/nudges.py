"""The four in-app nudges, and only these four: prices not updating, a plan step due, facts gone old, a SIP missed.

Built on request from what the app already knows; nothing is sent anywhere. Each kind has a switch in settings
(missing switch = on), and each nudge can be dismissed (the dismissal is kept, so it does not come back).
"""

from __future__ import annotations

from datetime import date

from finadvisor.advisor.overview import ACTION_WORDS, add_months
from finadvisor.calc.money import inr

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PROFILE_OLD_DAYS = 183           # six months
# nudge kind -> the settings switch that controls it
SWITCH = {"prices_stale": "data_refresh", "step_due": "plan_reminders", "profile_old": "profile_reminders",
          "sip_missed": "sip_reminders"}


def _day(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def build(*, today: date, prefs: dict, holdings: list[dict], plan: dict | None, profile_confirmed_on: date | None,
          sips: list[dict], dismissed: set[str]) -> list[dict]:
    out: list[dict] = []

    def add(kind: str, key: str, title: str, body: str, tab: str | None):
        nid = f"{kind}:{key}"
        if prefs.get(SWITCH[kind], True) and nid not in dismissed:
            out.append({"id": nid, "kind": kind, "title": title, "body": body, "to": "/money" if tab else "/", "tab": tab})

    stale = [h for h in holdings if h.get("stale") and h.get("price_date")]
    if stale:
        oldest = min(h["price_date"] for h in stale)
        n = len(stale)
        add("prices_stale", oldest, "Prices have not updated",
            f"{n} holding{'' if n == 1 else 's'} still show{'s' if n == 1 else ''} a price from {_day(date.fromisoformat(oldest))} or "
            "earlier. Values and gains use those prices until newer ones arrive.", "Overview")

    if plan and not plan.get("stale"):
        month_end = add_months(today, 1).isoformat()                     # the first day of next month
        due = next((s for s in plan["steps"] if s["status"] in ("suggested", "pending") and s["starts_on"] < month_end), None)
        if due:
            what = ACTION_WORDS.get(due["action"], due["action"].replace("_", " "))
            what = what[0].upper() + what[1:] + (f" for {due['goal']}" if due.get("goal") else "")
            amount = f" {inr(due['monthly'])} a month." if due["monthly"] else ""
            add("step_due", f"{plan['advice_run_id']}:{due['order']}:{today.year}-{today.month:02d}",
                f"This month: {what.lower()}", f"Step {due['order']} of {plan['total']} in your plan. {what}.{amount}".strip(), None)

    if profile_confirmed_on and (today - profile_confirmed_on).days > PROFILE_OLD_DAYS:
        add("profile_old", profile_confirmed_on.isoformat(), "Are your facts still right?",
            f"You last confirmed your income, expenses and loans on {_day(profile_confirmed_on)}. A plan is only as good "
            "as the facts under it.", "Facts")

    for sip in sips:
        if sip["status"] == "missed":
            add("sip_missed", f"{sip['id']}:{sip['next_expected']}", "A SIP instalment has not arrived",
                f"Your {inr(sip['amount'])} SIP in {sip['instrument']['name']} was expected around "
                f"{_day(date.fromisoformat(sip['next_expected']))}. If you stopped it, mark it stopped; if it went "
                "through, add the purchase.", "Funds")
    return out
