"""What the home page shows, built from the confirmed profile and the stored plan. Pure functions, no LLM.

Every rupee, share and date on the home page comes from here or from the engines; the web app only displays them.
"""

from __future__ import annotations

from datetime import date

from finadvisor.advisor.profile import Profile

OPEN = ("suggested", "pending")


def cash_flow(p: Profile) -> dict:
    """Where a month's take-home goes. `left_over` is Profile.monthly_surplus, the amount the planner works with, so
    the number on the home page is the number the advice uses. `widths` are the strip's segment sizes (they sum to 1)."""
    take, emis, expenses = p.take_home_monthly, p.total_emi, p.expenses_monthly
    left = p.monthly_surplus
    short = max(0.0, expenses + emis - take)
    whole = max(take, expenses + emis)
    widths = ({"emis": emis / whole, "expenses": expenses / whole, "left_over": left / whole} if whole > 0 else None)
    return {"take_home": take, "emis": emis, "expenses": expenses, "left_over": left, "short_by": short, "widths": widths}


def add_months(d: date, n: int) -> date:
    """The first day of the month `n` months after `d`'s month."""
    k = d.year * 12 + (d.month - 1) + n
    return date(k // 12, k % 12 + 1, 1)


def step_key(step: dict) -> str:
    """The key a plan step is stored under as a recommendation (api/store._recommend)."""
    return step["action"] + (f":{step['goal_id']}" if step.get("goal_id") else "")


def plan_overview(plan: dict, made_on: date, recs: dict[str, dict]) -> dict:
    """The stored plan as a timeline. Month 1 of the plan is the month it was made. `recs` maps a step's key to its
    latest recommendation ({id, status}); a step without one counts as suggested."""
    steps = []
    last = 0
    goal_names = {b["id"]: b["name"] for b in plan.get("buckets") or []}
    for s in plan["steps"]:
        start, n = int(s.get("start_month") or 1), int(s.get("months") or 0)
        rec = recs.get(step_key(s), {})
        end = start + n - 1 if n else None
        last = max(last, end or start)
        # dated: runs for a set number of months; ongoing: investing, with no end; one_off: done once (buy a cover)
        kind = "dated" if n else ("ongoing" if s["action"] == "invest" else "one_off")
        steps.append({
            "order": s["order"], "action": s["action"], "text": s["text"], "rule": s.get("rule"), "kind": kind,
            "goal": goal_names.get(s.get("goal_id")),            # what an investing step is for
            "monthly": s.get("monthly") or 0.0, "months": n, "start_month": start, "end_month": end,
            "starts_on": add_months(made_on, start - 1).isoformat(),
            "ends_on": add_months(made_on, end - 1).isoformat() if end else None,
            "recommendation_id": rec.get("id"), "status": rec.get("status", "suggested"),
        })
    invest_start = int(plan.get("invest_start_month") or 1)
    # room after the last dated step so the open-ended investing bar is visible; at least a year on the axis
    horizon = max(12, last + 3, invest_start + 5)
    for s in steps:
        s["offset"] = (s["start_month"] - 1) / horizon
        end = {"dated": s["end_month"], "ongoing": horizon, "one_off": s["start_month"]}[s["kind"]]
        s["width"] = (end - s["start_month"] + 1) / horizon
    nxt = next((s["order"] for s in steps if s["status"] in OPEN), None)
    return {
        "steps": steps,
        "total": len(steps),
        "done": sum(s["status"] == "done" for s in steps),
        "skipped": sum(s["status"] == "skipped" for s in steps),
        "next_order": nxt,
        "horizon_months": horizon,
        "axis": [{"month": m, "label_on": add_months(made_on, m - 1).isoformat(), "offset": (m - 1) / horizon}
                 for m in range(1, horizon + 1, 3 if horizon <= 24 else 6)],
        "monthly_surplus": plan["monthly_surplus"],
        "investing_monthly": plan["investing_monthly"],
        "invest_start_month": invest_start,
        "invest_starts_on": add_months(made_on, invest_start - 1).isoformat(),
        "notes": plan.get("notes") or [],
    }


def goal_progress(p: Profile, buckets: list[dict] | None) -> list[dict]:
    """Each goal's funded share today (saved so far against the cost in today's rupees) and, where the stored plan
    covers the goal, the monthly amount it needs and the amount the plan gives it."""
    by_id = {b["id"]: b for b in buckets or []}
    out = []
    for g in sorted(p.goals, key=lambda g: g.horizon_years):
        b = by_id.get(g.id, {})
        out.append({
            "goal_id": g.id, "name": g.name, "target_today": g.target_today, "saved_so_far": g.saved_so_far,
            "funded": min(1.0, g.saved_so_far / g.target_today) if g.target_today > 0 else 0.0,
            "horizon_years": g.horizon_years, "target_future": b.get("target_future"),
            "sip_needed": b.get("sip_needed"), "monthly_assigned": b.get("monthly") if b else None,
            "fundable": b.get("fundable"), "shortfall": b.get("shortfall") or 0.0,
        })
    return out


def health_history(snapshots: list[dict], now: dict | None = None, limit: int = 12) -> list[dict]:
    """One point per profile version (its latest snapshot), oldest first. `snapshots` are oldest first. `now` is the
    check on the current facts; it becomes the last point when the current version has no snapshot yet (snapshots
    are taken when advice is given), so the line always ends at the score shown beside it."""
    latest: dict = {}
    for snap in snapshots:
        latest[snap["profile_version"]] = snap
    if now is not None and now["profile_version"] not in latest:
        latest[now["profile_version"]] = now
    return sorted(latest.values(), key=lambda x: x["at"])[-limit:]
