"""The advisor pipeline entry point, shared by the website (via the API) and the experiment runner.

capacity -> willingness -> suitability -> gate -> planner (LLM chooses, calculators compute) -> audit -> output
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

import httpx
from typing import Callable

from finadvisor.advisor import auditor, cards, check as check_mod, compose, extract as extract_mod, fundfinder, numbers, \
    pressure, wishes
from finadvisor.advisor.capacity import assess as assess_capacity
from finadvisor.advisor.core import plan_once
from finadvisor.advisor.gate import RISK_LABEL, gate
from finadvisor.advisor.health import health_card
from finadvisor.advisor.plan import GENERAL
from finadvisor.advisor.profile import Profile, missing_fields
from finadvisor.advisor.prompts import ALL as TEMPLATES, EXPLAIN, EXPLAIN_WORDS, LEARN
from finadvisor.advisor.router import route as route_message
from finadvisor.llm.base import LLM, Generation, require_self_hosted

Emit = Callable[[str, dict], None]
Retriever = Callable[[str, int], list[dict]]
News = Callable[[list[str], int], dict]          # products in the answer, k -> cached headlines
Funds = Callable[[], dict | None]                 # the fund finder snapshot (display only; see advisor/fundfinder.py)

MODEL_DOWN = ("FinAdvisor's language model isn't reachable right now, so I can't write an explanation. Please try again "
              "in a minute.")
LEVEL = {"low": "Low", "medium": "Medium", "high": "High"}
GOAL_WORDS = re.compile(r"\bgoals?\b|\btimeline|\bhorizon", re.I)
# Promises of future suitability ("once that's done we can explore stocks"): the explainer must not make them.
PROMISE_WORDS = re.compile(r"\b(we|you) (can|could|will) (then )?(explore|reconsider|revisit|consider|look at|move on)"
                           r"|\bonce (you|that|this|it)\b[^.]*\b(we|you) (can|could)\b"
                           r"|\b(we|i|you)('ll| will| can) (revisit|reconsider|look at|explore|consider)\b"
                           r"|\bwhen your (risk )?profile allows\b|\b(later|in future|in the future|down the line)\b[^.]*"
                           r"\b(small[- ]?caps?|stocks?|equity|index fund|f&o|crypto)\b", re.I)
# How prose refers to each shelf product (for the product guard on the explanation).
PRODUCT_NAMES = {
    "fixed_deposit": r"\bfixed deposits?\b|\bfds?\b", "recurring_deposit": r"\brecurring deposits?\b|\brds?\b",
    "ppf": r"\bppf\b|public provident", "epf_vpf": r"\b[ev]pf\b|employees'? provident|voluntary provident",
    "liquid_fund": r"\bliquid (mutual )?funds?\b", "short_duration_debt_fund": r"short[- ]duration|\bdebt funds?\b",
    "nps": r"\bnps\b|national pension", "hybrid_baf": r"balanced advantage|\bhybrid\b", "gold_etf_fund": r"\bgold\b",
    "large_cap_index_fund": r"\bindex funds?\b|nifty 50 (index )?funds?", "flexi_cap_fund": r"flexi[- ]?cap",
    "elss": r"\belss\b|tax[- ]saving funds?", "mid_small_cap_fund": r"small[- ]?caps?|mid[- ]?caps?",
    "direct_equity": r"individual (stocks?|shares)|direct (equity|shares)", "fno": r"f&o|futures and options",
    "crypto": r"\bcrypto|bitcoin",
}
# Cards shown in the reply itself; the rest (full plan, goals, health check, what-if) sit under "Details".
MAIN_CARDS = {"not_yet", "check_ok", "profile", "questionnaire", "followups", "evidence"}
PROMPT_JARGON = re.compile(r"\b(the )?(PLAN FACTS|ALREADY TOLD)\b")
DANGLING = re.compile(r"^\s*(?:(?:then|next|lastly|finally|also|after that|additionally)\s*,?\s*)+", re.I)

STEP_WORDS = {
    "buy_health_cover": "Get health insurance cover; medical bills are the most common reason savings run out.",
    "buy_term_cover": "Get term life cover, because people depend on this income.",
    "clear_card_dues": "Pay the full credit-card bill every month; card interest is the most expensive debt.",
    "repay_costly_loan": "Prepay the costly personal or BNPL loan before investing.",
    "build_emergency_fund": "Build the emergency fund in a savings account or liquid fund.",
    "no_new_emi": "Take no new EMI or BNPL, and bring EMIs down below the limit.",
    "deploy_excess_savings": "Savings above the emergency fund can join the same long-term mix gradually, in parts, "
                             "not all on one day.",
}


def step_words(plan, bundle) -> list[str]:
    """The plan steps in words, without any amounts, for the number-free explainer (template explain_words)."""
    names = {p["id"]: p["name"] for p in bundle.shelf["products"]}
    buckets = {b.id: b for b in plan.buckets}
    out = []
    for i, s in enumerate(plan.steps):
        first = "Then: " if i else "First: "
        if s.action == "invest":
            b = buckets.get(s.goal_id or GENERAL)
            mix = [names.get(m.product_id, m.product_id) for m in (b.mix if b else []) if m.share > 0]
            kinds = ", ".join(mix[:-1]) + " and " + mix[-1] if len(mix) > 1 else (mix[0] if mix else "the plan's mix")
            out.append(f"{first}Invest for the goal '{b.name}' in {kinds}." if s.goal_id and b else
                       f"{first}Invest the rest for the long term in {kinds}.")
        elif s.action == "build_emergency_fund" and s.monthly <= 0:
            out.append(f"{first}The emergency fund can't grow yet because expenses use all of the take-home pay; "
                       "cutting expenses comes first.")
        else:
            out.append(first + STEP_WORDS.get(s.action, s.action.replace("_", " ") + "."))
    return out
FUND_WORDS = re.compile(r"\b(fund|funds|scheme|schemes|mutual|sip|amc)\b", re.I)


def plan_summary(final, profile: Profile, question: str, bundle) -> str:
    """Fixed, accurate opening for a plan answer: why these products, what is held back, what is missing."""
    rules = bundle.rules
    parts = []
    cap = final.capacity.level if final.capacity else None
    will = final.willingness
    max_risk = RISK_LABEL[rules["suitability"]["max_risk"][final.suitability]]
    if cap and will and will.score is not None:
        capped = ", capped at Medium until you have investing experience" if will.capped_by_experience else ""
        parts.append(f"Your capacity for loss is {LEVEL[cap]} and your risk questionnaire scores {will.score} of 47 "
                     f"({LEVEL[will.band_level]}{capped}), so your plan uses products rated up to {max_risk} risk.")
    blocked = [d for d in final.decisions if not d.allowed and d.product.get("plannable")]
    held = [d.product["name"] for d in blocked if any(r.startswith("its risk level") for r in d.reasons)]
    if held:
        names = held[0] if len(held) == 1 else ", ".join(held[:-1]) + " and " + held[-1]
        verb = "is held back because it is" if len(held) == 1 else "are held back because they are"
        parts.append(f"{names} {verb} rated above that.")
    salaried = [d.product["name"] for d in blocked if "available to salaried employees only" in d.reasons
                and d.product["name"] not in held]
    if salaried:
        parts.append(f"{' and '.join(salaried)} is left out because it is for salaried employees only.")
    if not profile.goals:
        parts.append("You haven't added goals with dates yet, so long-term money sits in one standard mix. Add a goal "
                     "such as a home or retirement on your profile and FinAdvisor sizes a monthly amount for each.")
    if FUND_WORDS.search(question):
        # Answer "which mutual funds?" directly with the fund categories the plan actually uses.
        names = {p["id"]: p["name"] for p in bundle.shelf["products"]}
        kinds = {p["id"]: p["kind"] for p in bundle.shelf["products"]}
        funds = list(dict.fromkeys(names[m.product_id] for b in final.plan.buckets for m in b.mix
                                   if m.share > 0 and kinds.get(m.product_id) == "fund"))
        if funds:
            listed = funds[0] if len(funds) == 1 else ", ".join(funds[:-1]) + " and " + funds[-1]
            parts.append(f"The mutual fund categories in your plan are: {listed}.")
        parts.append("FinAdvisor suggests fund categories, not specific schemes or fund houses.")
    return " ".join(parts)


NEWS_NOTE = ("News is shown for context only and never changes your plan: strong headlines are not a reason to invest "
             "more, and weak ones are not a reason to stop a SIP.")
SNIPPET_CHARS = 360
RULE_TOPICS = {"R1": "emergency fund liquid fund", "R2": "term life insurance cover", "R3": "health insurance 80D",
               "R4": "credit card dues personal loan", "R5": "loan EMI prepayment foreclosure"}


GREETING_TEXT = ("Hi! I can explain money topics, check whether something suits you, or build a plan from your "
                 "saved profile. What would you like to do?")


@dataclass
class TurnInput:
    text: str
    confirmed: Profile | None
    profile_version: int | None = None
    earlier_user_turns: list[str] = field(default_factory=list)
    forced_route: str | None = None
    # Loads what the person already holds ([{"product_id", "value"}]); the website passes one, experiments don't.
    holdings: Callable[[], list[dict]] | None = None


@dataclass
class TurnOutput:
    route: str
    text: str = ""
    cards: list[dict] = field(default_factory=list)
    advice: dict | None = None
    proposed_profile: dict | None = None
    sources: list[dict] = field(default_factory=list)
    status: str = "complete"           # complete | stopped | error
    generations: list[Generation] = field(default_factory=list)
    latency_s: float = 0.0


class Advisor:
    def __init__(self, bundle, llm: LLM, retriever: Retriever | None = None, real_users: bool = False,
                 news: News | None = None, funds: Funds | None = None):
        if real_users:
            require_self_hosted(llm)
        self.bundle = bundle
        self.llm = llm
        self.retriever = retriever
        self.news = news
        self.funds = funds

    # ------------------------------------------------------------------ public
    def turn(self, inp: TurnInput, emit: Emit, cancel: threading.Event | None = None) -> TurnOutput:
        t0 = time.perf_counter()
        r = inp.forced_route or route_message(inp.text).kind
        emit("route", {"route": r})
        out = TurnOutput(route=r)
        try:
            if r == "chat":
                out.text = GREETING_TEXT
                emit("token", {"text": out.text})
            elif r == "learn":
                self._learn(inp, emit, cancel, out)
            elif r == "check":
                self._check(inp, emit, cancel, out)
            else:
                self._plan(inp, emit, cancel, out)
        except Exception as e:  # noqa: BLE001 - surfaced to the user as an error state with retry
            out.status = "error"
            msg = (MODEL_DOWN if isinstance(e, httpx.TransportError)
                   else "Something went wrong while preparing this answer. Please try again.")
            emit("error", {"message": msg, "detail": type(e).__name__})
            raise
        finally:
            out.latency_s = round(time.perf_counter() - t0, 3)
        if cancel is not None and cancel.is_set():
            out.status = "stopped"
        return out

    def run_plan(self, profile: Profile, wish: str | None = None, progress: Callable[[str], None] | None = None):
        """Headless entry for experiments: same code as the website's Plan route."""
        core = plan_once(profile, self.bundle, self.llm, wish=wish)
        result = auditor.audit(core, self.bundle, self.llm, progress=progress)
        return core, result

    # ------------------------------------------------------------------ routes
    def _needs_profile(self, inp: TurnInput, emit: Emit, out: TurnOutput, purchase: bool) -> Profile | None:
        """Extraction + confirmation gate. Returns the confirmed profile, or None after emitting the card to confirm."""
        st = self.bundle.pipeline["stages"]
        if st["extraction"]:
            emit("stage", {"stage": "extraction", "status": "running"})
            try:
                proposed, changed, gen = extract_mod.extract(self.llm, inp.text, inp.confirmed, exclude_purchase=purchase)
            except httpx.TransportError:   # model unreachable: skip reading new facts; confirmed facts still work
                proposed, changed, gen = (inp.confirmed or Profile()).model_dump(), [], None
            if gen:
                out.generations.append(gen)
            emit("stage", {"stage": "extraction", "status": "done"})
            if changed or inp.confirmed is None:
                card = {"type": "profile", "proposed": proposed, "changed": changed, "requires_confirmation": True}
                out.cards.append(card)
                out.proposed_profile = proposed
                emit("card", card)
                out.text = ("I noted these details. Please check them on the profile card and confirm; I only use "
                            "facts you have confirmed." if changed else
                            "Let's set up your financial profile first. Fill in the card below and confirm it.")
                emit("token", {"text": out.text})
                return None
        if inp.confirmed is None:
            out.text = "Please confirm your profile first."
            emit("token", {"text": out.text})
            return None
        missing = missing_fields(inp.confirmed)
        if missing:
            if "gl_answers" in missing:
                card = {"type": "questionnaire", "items": self._questionnaire(), "answers": inp.confirmed.gl_answers}
                out.text = ("Before I plan, I need your answers to 13 short questions about risk. They measure how "
                            "much ups and downs you are comfortable with.")
            else:
                card = {"type": "profile", "proposed": inp.confirmed.model_dump(), "changed": [],
                        "requires_confirmation": True, "missing": missing}
                out.text = "A few details are missing from your profile. Please complete the card."
            out.cards.append(card)
            emit("card", card)
            emit("token", {"text": out.text})
            return None
        return inp.confirmed

    def _plan(self, inp: TurnInput, emit: Emit, cancel, out: TurnOutput) -> None:
        profile = self._needs_profile(inp, emit, out, purchase=False)
        if profile is None:
            return
        reading = pressure.read(inp.text, inp.earlier_user_turns)
        emit("stage", {"stage": "capacity", "status": "running"})
        try:
            core = plan_once(profile, self.bundle, self.llm, wish=inp.text if reading.is_pressure else None)
            out.generations += core.generations
            emit("stage", {"stage": "capacity", "status": "done", "level": core.capacity.level if core.capacity else None})
            emit("stage", {"stage": "planner", "status": "done"})
            emit("stage", {"stage": "audit", "status": "running"})
            result = auditor.audit(core, self.bundle, self.llm,
                                   progress=lambda msg: emit("stage", {"stage": "audit", "status": "running", "detail": msg}))
        except httpx.TransportError:
            # Model unreachable: every number comes from code anyway, so show the deterministic safe plan, labelled.
            core = plan_once(profile, self.bundle, None, use_safe_mix=True)
            result = auditor.AuditResult("fallback", core, fallback_reason="model_unavailable")
            emit("stage", {"stage": "capacity", "status": "done", "level": core.capacity.level if core.capacity else None})
        out.generations += [g for g in result.generations if g not in out.generations]
        final = result.final
        emit("stage", {"stage": "audit", "status": "done", "result": result.status})

        cap = final.capacity or assess_capacity(profile, self.bundle.rules)
        hc = health_card(profile, cap, self.bundle.rules)
        pc = cards.plan_card(final.plan, result.status)
        gcs = cards.goal_cards(final.plan, profile, self.bundle)
        wi = {"type": "what_if", "base": cards.what_if(profile, {}, self.bundle)["before"],
              "twins": cards.twin_whatifs(result),
              "sliders": {"take_home_monthly": profile.take_home_monthly, "expenses_monthly": profile.expenses_monthly,
                          "liquid_savings": profile.liquid_savings, "dependants": profile.dependants, "new_emi": 0}}
        new_cards = [hc, pc, *gcs, wi]
        conflict = wish = None
        in_plan = list(dict.fromkeys(m.product_id for b in final.plan.buckets for m in b.mix))
        if reading.products:
            nc = check_mod.check(profile, self.bundle, reading.products, inp.text)
            if nc["verdict"] != "fits":
                new_cards.insert(0, nc)
                conflict = nc["conflict"]
            wish = wishes.frame(nc, {d.id: d for d in final.decisions}, cap.rule_ids, self.bundle, in_plan,
                                reading.types, [g.horizon_years for g in profile.goals])
        evidence = self._evidence(inp.text, reading.products + in_plan, emit, cap.rule_ids)
        if evidence:
            new_cards.append(evidence)
        # Question-first reply: a direct answer, the steps that matter for it, and a few personal reasons. The full
        # plan, health check and what-if are details the app shows on request.
        held = []
        if inp.holdings is not None:
            try:
                held = inp.holdings()
            except Exception:  # noqa: BLE001 - the reply simply leaves out "what you already have"
                held = []
        # The real schemes of each fund type in the plan (display only: built from the plan, never fed back into it).
        snap = self.funds() if self.funds is not None else None
        monthly: dict[str, float] = {}
        for b in final.plan.buckets:
            for m in b.mix:
                monthly[m.product_id] = monthly.get(m.product_id, 0) + m.monthly
        # Largest monthly amount first, the order the reply names the fund types in
        fund_cards = fundfinder.cards_for(sorted(in_plan, key=lambda p: -monthly.get(p, 0)), snap)
        comp = compose.answer(inp.text, final, profile, cap, self.bundle, held, fund_lists=bool(fund_cards), snap=snap)
        if comp["intent"] == "compare":
            wish = conflict = None   # the comparison covers every product named; the "not yet" card still shows
        new_cards += fund_cards
        new_cards.append({"type": "followups", "items": comp["followups"]})
        for c in new_cards:
            c.setdefault("show", "main" if c["type"] in MAIN_CARDS else "details")
            if comp["intent"] == "emergency" and c["type"] == "health_check":
                c["show"] = "main"
            if comp["intent"] == "funds" and c["type"] == "fund_finder":
                c["show"] = "main"
        why = cards.why_panel(final, result, {"pressure": {"types": reading.types, "products": reading.products}})
        for c in new_cards:
            out.cards.append(c)
            emit("card", c)
        emit("why", why)

        lead = compose.render(comp, with_short=wish is None)
        facts = [s["text"] for s in pc["steps"]]
        # Product guard: the explanation may name only products in the plan or in the person's request (the 3B model
        # once told a Low-capacity person to "start investing in a balanced advantage or flexi-cap fund").
        # A requested product counts only if the plan uses it: the deterministic answer already covers a blocked wish,
        # and the model once wrote "after that, we'll start investing in mid- and small-cap funds".
        allowed = set(in_plan) | {"savings_account"}
        other = [PRODUCT_NAMES[p] for p in PRODUCT_NAMES if p not in allowed]
        bans = [PROMISE_WORDS.pattern, *other] + ([] if profile.goals else [GOAL_WORDS.pattern])
        ban = re.compile("|".join(f"(?:{b})" for b in bans), re.I)
        # The model explains the plan steps; a reply that lists none (switch to Direct, no card debt, ...) has nothing
        # for it to explain, and its paragraph about the plan read as off-topic.
        self._explain(facts, conflict, inp.text, new_cards, emit, cancel, out, lead=lead, ban=ban, wish=wish,
                      word_facts=step_words(final.plan, self.bundle),
                      docs=self._docs_for_prompt(evidence), model=bool(comp["todo"]))
        out.advice = self._record("plan", inp, profile, final, result, why, reading, out)
        out.advice.update(wish=wish, evidence=evidence, fund_finder=fundfinder.record(fund_cards, snap),
                          compose={"intent": comp["intent"], "holdings": held,
                                                                 "summary": plan_summary(final, profile, inp.text, self.bundle)})

    def _check(self, inp: TurnInput, emit: Emit, cancel, out: TurnOutput) -> None:
        products = pressure.products_in(inp.text)
        # A pressure turn shows the (unchanged) plan with the conflict, so it goes through the Plan route.
        if not products or pressure.read(inp.text, inp.earlier_user_turns).is_pressure:
            out.route = "plan"
            emit("route", {"route": "plan"})
            return self._plan(inp, emit, cancel, out)
        profile = self._needs_profile(inp, emit, out, purchase=True)
        if profile is None:
            return
        reading = pressure.read(inp.text, inp.earlier_user_turns)
        emit("stage", {"stage": "gate", "status": "running"})
        card = check_mod.check(profile, self.bundle, products, inp.text)
        emit("stage", {"stage": "gate", "status": "done"})
        cap = assess_capacity(profile, self.bundle.rules)
        hc = health_card(profile, cap, self.bundle.rules)
        decisions = {d.id: d for d in gate(card["suitability"], cap.rule_ids, profile, self.bundle.shelf, self.bundle.rules)}
        wish = wishes.frame(card, decisions, cap.rule_ids, self.bundle, pressure_types=reading.types,
                            goal_years=[g.horizon_years for g in profile.goals])
        evidence = self._evidence(inp.text, products, emit, cap.rule_ids)
        nexts = {"type": "followups", "items": ["Make me a money plan", "Which mutual funds suit me?"]}
        for c in (card, hc, evidence, nexts):
            if c:
                c.setdefault("show", "main" if c["type"] in MAIN_CARDS else "details")
                out.cards.append(c)
                emit("card", c)
        why = {"capacity": cap.to_dict(), "suitability": card["suitability"],
               "rules": [h.__dict__ for h in cap.triggered], "check": card,
               "pressure": {"types": reading.types, "products": reading.products}, "audit": {"status": "not_applicable"}}
        emit("why", why)
        facts = [x["text"] for x in card["changes"]] + card["blockers"]
        # The deterministic answer and advice cover a Check fully; a model paragraph only repeated them, sometimes
        # wrongly, so Check answers carry no model prose.
        self._explain(facts, card.get("conflict"), inp.text, [card, hc], emit, cancel, out, wish=wish, model=False)
        out.advice = {
            "route": "check", "profile_version": inp.profile_version, "profile": profile.model_dump(),
            "capacity": cap.to_dict(), "suitability": card["suitability"], "check": card,
            "rules": sorted(cap.rule_ids), "pressure": why["pressure"], "why": why, "wish": wish, "evidence": evidence,
            **self._identity(out),
        }

    def _learn(self, inp: TurnInput, emit: Emit, cancel, out: TurnOutput) -> None:
        chunks: list[dict] = []
        if self.retriever is not None:
            emit("stage", {"stage": "retrieval", "status": "running"})
            try:
                chunks = self.retriever(inp.text, 4)
            except Exception:  # noqa: BLE001 - the answer degrades to "sources unavailable"
                chunks = []
            emit("stage", {"stage": "retrieval", "status": "done", "count": len(chunks)})
        # One numbered source per document, so the model's [n] citations match the chips under the answer.
        docs: dict[str, dict] = {}
        for c in chunks:
            d = docs.setdefault(c.get("source"), {**c, "text": ""})
            d["text"] = (d["text"] + "\n" + c["text"]).strip()
        chunks = list(docs.values())
        out.sources = [{"n": i + 1, **{k: c.get(k) for k in ("id", "title", "source")}} for i, c in enumerate(chunks)]
        emit("sources", {"sources": out.sources})
        if not chunks:
            out.text = ("I couldn't find this in FinAdvisor's document library, so I won't guess. Try rephrasing, "
                        "or ask about a specific product such as PPF, ELSS, SIPs, NPS or health insurance.")
            emit("token", {"text": out.text})
            return
        ctx = "\n\n".join(f"[{i + 1}] {c.get('title', '')}\n{c['text']}" for i, c in enumerate(chunks))
        prompt = f"SOURCES\n{ctx}\n\nQUESTION: {inp.text}"
        allowed = numbers.collect([c["text"] for c in chunks] + [inp.text])
        try:
            self._stream(LEARN.system, prompt, "learn", LEARN.id, allowed, emit, cancel, out)
        except httpx.TransportError:
            out.text = MODEL_DOWN + " The documents that match your question are listed below."
            emit("token", {"text": out.text})

    # ------------------------------------------------------------------ helpers
    def _explain(self, facts: list[str], conflict: str | None, question: str, card_list: list[dict], emit, cancel, out,
                 lead: str | None = None, ban: re.Pattern | None = None, wish: dict | None = None,
                 docs: list[dict] | None = None, model: bool = True, word_facts: list[str] | None = None):
        # Deterministic paragraphs first: the answer to what was asked, FinAdvisor's advice, then the plan summary.
        # The model only adds a short explanation after them.
        fixed = [wish["answer"], "**My advice:** " + wish["advice"]] if wish else [conflict]
        told = [t for t in (*fixed, lead) if t]
        for t in told:
            out.text += t + "\n\n"
            emit("token", {"text": t + "\n\n"})
        if not model:
            return
        words_only = self.bundle.pipeline.get("explainer", {}).get("numbers") == "none"
        if words_only and word_facts is not None:
            # No amounts in the prompt at all, so the model has none to misplace (and fewer sentences get dropped).
            facts = word_facts
            told = ["the result of their risk questionnaire and capacity check, which products are held back, and "
                    "FinAdvisor's answer and advice on their request"] if told else []
        prompt = "PLAN FACTS\n" + "\n".join(f"- {f}" for f in facts)
        if docs:
            # Background for wording only: numbers in these passages are not approved, so sentences using them are dropped.
            prompt = ("BACKGROUND (library passages; use them to explain what products are, never quote their numbers)\n"
                      + "\n".join(f"- {d['title']}: {d['snippet']}" for d in docs) + "\n\n" + prompt)
        if told:
            prompt += "\n\nALREADY TOLD THE PERSON (do not repeat): " + " ".join(told)
        prompt += f"\n\nUSER ASKED: {question}"
        template = EXPLAIN
        # Library passages and fund lists hold numbers the plan didn't produce, so they never approve a number.
        allowed = numbers.collect([facts, [c for c in card_list if c.get("type") not in ("evidence", "fund_finder")],
                                   question, lead or ""])
        if words_only:
            # Amounts live on the plan card only: any sentence with a number (beyond small counts), ₹ or % is dropped.
            template, allowed = EXPLAIN_WORDS, set()
            ban = re.compile("|".join(x for x in (ban.pattern if ban else None, r"₹|%|\brs\.?\s?\d") if x), re.I)
        try:
            # Labelled, so the model's summary reads as a recap of the steps above rather than more advice.
            self._stream(template.system, prompt, "explain", template.id, allowed, emit, cancel, out, ban=ban,
                         heading="**In plain words**\n\n" if lead else None)
        except Exception as e:  # noqa: BLE001 - the cards already carry the plan; fall back to a fixed sentence
            text = ("Your plan is on the cards below, step by step. (" + MODEL_DOWN.split(",")[0] + ", so this is the "
                    "standard plan for your suitability level without a written explanation.)"
                    if isinstance(e, httpx.TransportError) else "Your plan is on the cards below, step by step.")
            out.text += text
            emit("token", {"text": text})

    def _stream(self, system, prompt, purpose, template, allowed, emit, cancel, out, ban: re.Pattern | None = None,
                heading: str | None = None):
        """`heading` is written before the first sentence that survives the guards (so no empty heading is left)."""
        t = time.perf_counter()
        dropped = []
        stream = self.llm.stream(system, prompt, purpose=purpose, template=template, cancel=cancel)
        after_gap = True          # at the start, or right after a dropped sentence
        for sentence, bad in numbers.guard_sentences(stream, allowed):
            if cancel is not None and cancel.is_set():
                break
            if bad:
                dropped.append({"numbers": bad})
                after_gap = True
                continue
            if ban is not None and ban.search(sentence):   # e.g. "your goals" when the person has none
                dropped.append({"banned": ban.search(sentence).group(0)})
                after_gap = True
                continue
            sentence = PROMPT_JARGON.sub("your plan", sentence)   # "based on the PLAN FACTS" -> "based on your plan"
            if after_gap:   # "Then, after that, cut expenses." with nothing before it reads broken
                sentence = DANGLING.sub("", sentence)
                sentence = sentence[:1].upper() + sentence[1:]
                after_gap = False
            if heading:
                sentence, heading = heading + sentence, None
            out.text += sentence
            emit("token", {"text": sentence})
        out.generations.append(Generation(purpose, template, round(time.perf_counter() - t, 3),
                                          {"dropped_sentences": dropped}))

    def _evidence(self, question: str, products: list[str], emit: Emit, rule_ids=()) -> dict | None:
        """The "What I looked at" card: library passages on the products in this answer, and cached market headlines."""
        cfg = self.bundle.pipeline.get("evidence", {})
        n_docs, n_news = cfg.get("documents", 0), cfg.get("headlines", 0)
        products = list(dict.fromkeys(products))
        docs: list[dict] = []
        if n_docs and self.retriever is not None:
            emit("stage", {"stage": "retrieval", "status": "running"})
            names = [p["name"] for pid in products for p in self.bundle.shelf["products"] if p["id"] == pid]
            # The advice often answers with a priority step (emergency fund, cover), so search for those topics too.
            topics = [RULE_TOPICS[r] for r in sorted(rule_ids) if r in RULE_TOPICS][:2]
            try:
                hits = self.retriever(" ".join([question, *topics, *names[:4]]), n_docs + 2)
            except Exception:  # noqa: BLE001 - the card then shows headlines only
                hits = []
            seen: set = set()
            for h in hits:
                if h.get("source") in seen:
                    continue
                seen.add(h.get("source"))
                text = " ".join(h["text"].split())
                cut = text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
                docs.append({"n": len(docs) + 1, "id": h.get("id"), "title": h.get("title"), "source": h.get("source"),
                             "snippet": cut})
                if len(docs) == n_docs:
                    break
            emit("stage", {"stage": "retrieval", "status": "done", "count": len(docs)})
        news = None
        if n_news and self.news is not None:
            try:
                news = {**self.news(products, n_news), "note": NEWS_NOTE}
            except Exception:  # noqa: BLE001 - headlines are optional context
                news = None
        if not docs and news is None:
            return None
        return {"type": "evidence", "documents": docs, "news": news,
                "library": "FinAdvisor's library of Indian regulatory and product guides"}

    def _docs_for_prompt(self, evidence: dict | None) -> list[dict] | None:
        if not evidence or not self.bundle.pipeline.get("evidence", {}).get("documents_in_prompt"):
            return None
        return evidence["documents"] or None

    def _questionnaire(self) -> list[dict]:
        return [{"n": i["n"], "text": i["text"], "options": [{"key": o["key"], "text": o["text"]} for o in i["options"]]}
                for i in self.bundle.willingness["items"]]

    def _identity(self, out: TurnOutput) -> dict:
        return {
            "model": self.llm.identity.to_dict() if self.llm else None,
            "templates": {**{t.name: t.id for t in TEMPLATES}, "wish": wishes.template_id(),
                          "compose": compose.template_id()},
            "versions": self.bundle.versions,
            "flags": self.bundle.pipeline["stages"],
            "generations": [g.to_dict() for g in out.generations],
        }

    def _record(self, route, inp, profile, final, result, why, reading, out) -> dict:
        return {
            "route": route,
            "profile_version": inp.profile_version,
            "profile": profile.model_dump(),
            "capacity": final.capacity.to_dict() if final.capacity else None,
            "willingness": final.willingness.to_dict() if final.willingness else None,
            "suitability": final.suitability,
            "rules": sorted(final.capacity.rule_ids) if final.capacity else [],
            "gated_out": why["gated_out"],
            "plan": final.plan.to_dict(),
            "audit": result.to_dict(),
            "pressure": {"types": reading.types, "products": reading.products},
            "why": why,
            **self._identity(out),
        }
