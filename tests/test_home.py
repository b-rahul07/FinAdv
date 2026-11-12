"""The home page's numbers: cash flow, the plan as a timeline, goal progress, health history."""

from datetime import date

from finadvisor.advisor import overview
from finadvisor.advisor.profile import Debt, Goal, Profile
from finadvisor.db import models  # noqa: F401  (registers the tables before the client fixture builds the database)
from test_api import PROFILE, client, events, login  # noqa: F401  (fixture)


def test_cash_flow_is_the_surplus_the_planner_uses():
    p = Profile(take_home_monthly=80_000, expenses_monthly=40_000,
                debts=[Debt(kind="car", outstanding=300_000, emi_monthly=12_000), Debt(kind="education", outstanding=1, emi_monthly=8_000)])
    c = overview.cash_flow(p)
    assert c == {"take_home": 80_000, "emis": 20_000, "expenses": 40_000, "left_over": 20_000, "short_by": 0,
                 "widths": {"emis": 0.25, "expenses": 0.5, "left_over": 0.25}}
    assert c["left_over"] == p.monthly_surplus
    over = overview.cash_flow(Profile(take_home_monthly=30_000, expenses_monthly=28_000,
                                      debts=[Debt(kind="personal", outstanding=1, emi_monthly=7_000)]))
    assert over["left_over"] == 0 and over["short_by"] == 5_000
    assert abs(sum(over["widths"].values()) - 1) < 1e-9          # the strip is full, with nothing left over
    assert overview.cash_flow(Profile())["widths"] is None


def test_add_months_crosses_years():
    assert overview.add_months(date(2026, 11, 12), 0) == date(2026, 11, 1)
    assert overview.add_months(date(2026, 11, 12), 2) == date(2027, 1, 1)
    assert overview.add_months(date(2026, 1, 31), 13) == date(2027, 2, 1)


PLAN = {"steps": [
    {"order": 1, "action": "buy_health_cover", "text": "Buy health cover.", "rule": "R3", "monthly": 0, "months": 0, "start_month": 1},
    {"order": 2, "action": "build_emergency_fund", "text": "Build the fund.", "rule": "R1", "monthly": 20_000, "months": 7, "start_month": 1},
    {"order": 3, "action": "invest", "text": "Invest for Retirement.", "rule": None, "monthly": 20_000, "months": 0, "start_month": 8,
     "goal_id": "ret"}],
    "monthly_surplus": 20_000, "investing_monthly": 20_000, "invest_start_month": 8, "notes": []}


def test_plan_overview_dates_progress_and_next_step():
    recs = {"buy_health_cover": {"id": "r1", "status": "done"}, "invest:ret": {"id": "r3", "status": "suggested"}}
    o = overview.plan_overview(PLAN, date(2026, 11, 12), recs)
    assert (o["total"], o["done"], o["next_order"]) == (3, 1, 2)        # step 2 has no recommendation yet: still open
    fund, invest = o["steps"][1], o["steps"][2]
    assert (fund["starts_on"], fund["ends_on"], fund["end_month"]) == ("2026-11-01", "2027-05-01", 7)
    assert invest["starts_on"] == o["invest_starts_on"] == "2027-06-01" and invest["ends_on"] is None
    assert invest["recommendation_id"] == "r3" and o["steps"][0]["status"] == "done"
    assert o["horizon_months"] == 13 and fund["offset"] == 0 and abs(fund["width"] - 7 / 13) < 1e-9
    assert abs(invest["offset"] + invest["width"] - 1) < 1e-9          # the open-ended bar runs to the end of the axis
    assert o["axis"][0] == {"month": 1, "label_on": "2026-11-01", "offset": 0}
    cover = o["steps"][0]
    assert (cover["kind"], fund["kind"], invest["kind"]) == ("one_off", "dated", "ongoing")
    named = overview.plan_overview({**PLAN, "buckets": [{"id": "ret", "name": "Retirement"}]}, date(2026, 11, 12), {})
    assert named["steps"][2]["goal"] == "Retirement" and named["steps"][0]["goal"] is None and invest["goal"] is None
    assert abs(cover["width"] - 1 / 13) < 1e-9                         # a one-off step is a single month on the axis
    all_done = overview.plan_overview(PLAN, date(2026, 11, 12), {k: {"id": k, "status": "done"} for k in
                                                                ("buy_health_cover", "build_emergency_fund", "invest:ret")})
    assert all_done["next_order"] is None and all_done["done"] == 3


def test_goal_progress_and_health_history():
    p = Profile(goals=[Goal(id="ret", name="Retirement", target_today=5_000_000, horizon_years=30, saved_so_far=500_000),
                       Goal(id="trip", name="Trip", target_today=200_000, horizon_years=2, saved_so_far=300_000)])
    g = overview.goal_progress(p, [{"id": "ret", "monthly": 9_000, "sip_needed": 12_000, "fundable": False, "shortfall": 3_000,
                                    "target_future": 2.0e7}])
    assert [x["goal_id"] for x in g] == ["trip", "ret"]                  # nearest first
    assert g[0]["funded"] == 1.0 and g[0]["sip_needed"] is None and g[0]["monthly_assigned"] is None
    assert g[1]["funded"] == 0.1 and g[1]["monthly_assigned"] == 9_000 and g[1]["shortfall"] == 3_000
    snaps = [{"at": "2026-01-01", "score": 3, "out_of": 7, "profile_version": 1},
             {"at": "2026-02-01", "score": 4, "out_of": 7, "profile_version": 1},
             {"at": "2026-03-01", "score": 6, "out_of": 7, "profile_version": 2}]
    assert [(h["score"], h["profile_version"]) for h in overview.health_history(snaps)] == [(4, 1), (6, 2)]
    now = {"at": "2026-04-01", "score": 7, "out_of": 7, "profile_version": 3}
    assert [h["score"] for h in overview.health_history(snaps, now)] == [4, 6, 7]       # facts newer than any advice
    assert [h["score"] for h in overview.health_history(snaps, {**now, "profile_version": 2})] == [4, 6]


def test_home_api_follows_profile_plan_and_step_status(client):
    h = login(client)
    empty = client.get("/api/home", headers=h).json()
    assert empty == {"profile_version": None, "cash_flow": None, "health": None, "health_history": [], "plan": None, "goals": []}

    client.put("/api/profile", json={"data": PROFILE}, headers=h)
    home = client.get("/api/home", headers=h).json()
    assert home["cash_flow"]["left_over"] == 20_000 and home["plan"] is None
    assert [h["score"] for h in home["health_history"]] == [home["health"]["score"]]     # the check on the facts as they are
    assert home["goals"][0]["name"] == "Retirement" and home["goals"][0]["funded"] == 0

    chat = client.post("/api/chats", json={}, headers=h).json()
    ev = events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Make me a plan for my money"}, headers=h))
    card = next(d for k, d in ev if k == "card" and d["type"] == "plan")
    home = client.get("/api/home", headers=h).json()
    plan = home["plan"]
    assert plan["total"] == len(card["steps"]) and plan["done"] == 0 and plan["next_order"] == 1 and plan["stale"] is False
    assert plan["monthly_surplus"] == home["cash_flow"]["left_over"] == card["monthly_surplus"]
    assert all(s["recommendation_id"] for s in plan["steps"]) and plan["chat_id"] == chat["id"]
    assert len(home["health_history"]) == 1 and home["health_history"][0]["score"] == home["health"]["score"]

    first = plan["steps"][0]
    client.patch(f"/api/recommendations/{first['recommendation_id']}", json={"status": "done"}, headers=h)
    plan = client.get("/api/home", headers=h).json()["plan"]
    assert plan["done"] == 1 and plan["next_order"] == 2 and plan["steps"][0]["status"] == "done"

    client.put("/api/profile", json={"data": {**PROFILE, "take_home_monthly": 60000}}, headers=h)
    home = client.get("/api/home", headers=h).json()
    assert home["plan"]["stale"] is True and home["cash_flow"]["left_over"] == 30_000    # facts moved on; the plan did not
    assert home["goals"][0]["monthly_assigned"] is None                                  # so its goal amounts are not shown
    assert [h["profile_version"] for h in home["health_history"]] == [1, 2]
    assert home["health_history"][-1]["score"] == home["health"]["score"]
