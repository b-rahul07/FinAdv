// Shapes returned by the API (finadvisor/api). Cards are built server-side from computed results.

export type ChatSummary = { id: string; title: string; pinned: boolean; created_at: string; updated_at: string };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  route: "learn" | "plan" | "check" | "chat" | "whatif" | "tax" | "track" | "ask" | null;
  cards: Card[];
  sources: Source[];
  status: "complete" | "stopped" | "error" | "streaming";
  advice_run_id: string | null;
  created_at: string;
  feedback: { rating: number; comment: string } | null;
  stages?: Stage[];
};

export type Stage = { stage: string; status: string; detail?: string; result?: string };
export type Source = { n: number; id: string; title: string; source: string };

export type Debt = { kind: string; label?: string; outstanding: number; rate_pa: number | null; emi_monthly: number };
export type Goal = { id: string; name: string; kind: string; target_today: number; horizon_years: number; saved_so_far: number };

export type Profile = {
  age: number | null;
  take_home_monthly: number;
  expenses_monthly: number;
  liquid_savings: number;
  debts: Debt[];
  card_dues_paid_in_full: boolean;
  dependants: number;
  life_cover: number;
  health_cover: number;
  goals: Goal[];
  salaried: boolean;
  experience: "none" | "beginner" | "intermediate" | "advanced";
  gl_answers: Record<string, string>;
  wishes: string[];
  /** Optional facts for tax estimates; absent until the person gives one. */
  tax?: { gross_salary_annual: number | null; deductions_80c: number | null; deductions_80d: number | null; nps_80ccd1b: number | null; hra_exemption_annual: number | null } | null;
};

export type HealthCheck = {
  type: "health_check";
  score: number;
  out_of: number;
  capacity_level: string;
  checks: { key: string; title: string; status: "pass" | "fail"; reason: string; rule: string }[];
};

export type PlanStep = {
  order: number;
  action: string;
  text: string;
  rule: string | null;
  monthly: number;
  months: number;
  start_month: number;
  target: number;
  goal_id: string | null;
};

export type PlanCard = {
  type: "plan";
  source: string;
  audit_status: string;
  monthly_surplus: number;
  investing_monthly: number;
  invest_start_month: number;
  rho: number;
  steps: PlanStep[];
  notes: string[];
};

export type GoalCard = {
  type: "goal";
  goal_id: string;
  name: string;
  target_today: number;
  target_future: number | null;
  horizon_years: number;
  saved_so_far: number;
  inflation_pa: number;
  assumed_return_pa: number | null;
  sip_needed: number | null;
  monthly_assigned: number;
  starts_month: number;
  fundable: boolean | null;
  shortfall: number;
  mix: { product_id: string; share: number; monthly: number }[];
};

export type NotYetCard = {
  type: "not_yet" | "check_ok";
  verdict: "not_yet" | "after_priorities" | "fits";
  product_id: string;
  product_name: string;
  conflict: string | null;
  blockers: string[];
  changes: { rule: string; text: string }[];
  suitability: string;
  capacity_level: string;
  willingness_level: string;
  fact?: { text: string; source: string };
  new_emi?: number;
  emi_ratio_now?: number;
  emi_ratio_after?: number;
};

export type WhatIfCard = {
  type: "what_if";
  base: Summary;
  twins: { relation: string; description: string; change: string; capacity: string; suitability: string; invest_start_month: number; rho: number }[];
  sliders: { take_home_monthly: number; expenses_monthly: number; liquid_savings: number; dependants: number; new_emi: number };
};

export type Summary = {
  capacity_level: string | null;
  suitability: string;
  rules: string[];
  invest_start_month: number;
  investing_monthly: number;
  rho: number;
  monthly_surplus: number;
};

export type WhatIfResult = {
  type: "what_if";
  illustrative: true;
  before: Summary;
  after: Summary;
  explanations: string[];
  after_plan: PlanCard;
};

export type ProfileCardT = { type: "profile"; proposed: Profile; changed: string[]; requires_confirmation: boolean; missing?: string[] };
export type QuestionnaireCard = { type: "questionnaire"; items: QItem[]; answers: Record<string, string> };
export type QItem = { n: number; text: string; options: { key: string; text: string }[] };

export type Headline = { headline: string; source: string; url: string | null; published: string | null; mood: string | null; confidence: number | null };

export type EvidenceCard = {
  type: "evidence";
  library: string;
  documents: { n: number; id: string; title: string; source: string; snippet: string }[];
  news: { as_of: string | null; stale: boolean; mood: string | null; source: string; model?: string; note: string; items: Headline[] } | null;
};

export type FollowupsCard = { type: "followups"; items: string[] };

/** One missing fact, asked once (advisor/converse.py). `then` is the question to ask again once it is saved. */
export type AskCard = { type: "ask"; field: string; question: string; unit: string; min: number; max: number; hint: string; then: string };

/** The answer to a follow-up "what if": today's facts against the changed ones, from the what-if engine. */
export type WhatIfAnswerCard = {
  type: "what_if_answer";
  label: string;
  changes: Record<string, number>;
  before: Summary;
  after: Summary;
  explanations: string[];
  apply: Profile | null;
  apply_note: string | null;
};

export type TaxRegime = {
  label: string;
  gross: number;
  standard_deduction: number;
  deductions: Record<string, number>;
  deductions_total: number;
  taxable: number;
  tax_before_rebate: number;
  rebate: number;
  surcharge: number;
  cess: number;
  total: number;
  marginal_rate: number;
};

export type TaxCard = {
  type: "tax";
  financial_year: string;
  as_of: string;
  gross: number;
  new: TaxRegime;
  old: TaxRegime;
  better: "new" | "old" | "same";
  saving: number;
  deductions: { deductions_80c: number; deductions_80d: number; nps_80ccd1b: number; hra_exemption_annual: number };
  deductions_known: boolean;
  then: string;
  source: string;
};

export type PlanChangeCard = { type: "plan_change"; lines: string[] };

/** One scheme in a fund finder list. Returns are fractions a year (CAGR); expense_ratio is in percent (0.74 = 0.74%). */
export type FundRow = {
  code: string;
  name: string;
  amc: string;
  category: string;
  nav: number;
  nav_date: string;
  expense_ratio: number | null;
  expense_ratio_date: string | null;
  since: string | null;
  returns: { "1y": number | null; "3y": number | null; "5y": number | null } | null;
};

/** The real schemes of one fund type in the plan, cheapest first. Display only; FinAdvisor never picks one. */
export type FundFinderCard = {
  type: "fund_finder";
  product_id: string;
  label: string;
  total: number;
  funds: FundRow[];
  checklist: string[];
  links: { label: string; url: string }[];
  note: string;
  sources: { nav: string; expense_ratio: string | null; returns: string };
  built_at: string;
  stale: boolean;
};

/** "main" cards sit in the reply; "details" cards (full plan, goals, health check, what-if) open on request. */
export type Card = (HealthCheck | PlanCard | GoalCard | NotYetCard | WhatIfCard | ProfileCardT | QuestionnaireCard | EvidenceCard | FundFinderCard | FollowupsCard
  | AskCard | WhatIfAnswerCard | TaxCard | PlanChangeCard) & {
  show?: "main" | "details";
};

export type ProfileView = {
  version: number | null;
  data: Profile;
  sources: Record<string, string>;
  missing: string[];
  health: HealthCheck | null;
  willingness: { score: number | null; level: string; band_level: string | null; capped_by_experience: boolean } | null;
  capacity?: Record<string, number | string | null>;
};

export type Me = {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  provider: string;
  is_demo: boolean;
  created_at: string;
  settings: { theme: "system" | "light" | "dark"; indian_grouping: boolean; research_opt_in: boolean; notifications: Record<string, boolean> };
};

export type Recommendation = {
  id: string;
  key: string;
  action: string;
  rule: string | null;
  title: string;
  monthly: number | null;
  months: number | null;
  status: "suggested" | "pending" | "done" | "skipped";
  advice_run_id: string | null;
  suggested_at: string;
};

export type Why = {
  capacity: Record<string, any> | null;
  willingness: Record<string, any> | null;
  suitability: string;
  rules: { rule: string; detail: string; goal_id: string | null }[];
  gated_out?: { product_id: string; name: string; reasons: string[] }[];
  audit: { status: string; attempts?: number; violations?: string[]; failed_relations?: string[]; relations_checked?: string[] };
  pressure?: { types: string[]; products: string[] };
};

export type Instrument = {
  id: string;
  kind: "stock" | "etf" | "sgb" | "mf";
  symbol: string | null;
  exchange: string | null;
  isin: string | null;
  name: string;
  amc: string | null;
  category: string | null;
  plan: string | null;
  option: string | null;
  expense_ratio: number | null;
  scheme_code: string | null;
};

export type Holding = {
  instrument: Instrument;
  asset_class: string;
  qty: number;
  avg_price: number;
  invested: number;
  price: number | null;
  prev_price: number | null;
  value: number | null;
  day_change: number | null;
  day_change_pct: number | null;
  unrealised: number | null;
  unrealised_pct: number | null;
  realised: number;
  xirr: number | null;
  xirr_note: string | null;
  first_buy: string | null;
  holding_days: number | null;
  long_term_qty: number;
  short_term_qty: number;
  week52: { low: number; high: number } | null;
  price_source: string | null;
  price_date: string | null;
  stale: boolean;
  weight: number | null;
};

export type HoldingsResp = {
  as_of: string;
  items: Holding[];
  summary: { invested: number; value: number; gain: number; day_change: number; unpriced: number; latest_price_date: string | null };
  loading: string[];
};

export type WatchRow = {
  id: string;
  instrument: Instrument;
  added_on: string;
  price_when_added: number | null;
  price_when_added_date: string | null;
  current_price: number | null;
  price_date: string | null;
  price_source: string | null;
  change_since_added: number | null;
  week52: { low: number; high: number } | null;
  stale: boolean;
};

export type TxRow = { id: string; instrument: Instrument; kind: "buy" | "sell"; trade_date: string; quantity: number; price: number; charges: number; note: string; source: string };

export type DashboardResp = {
  as_of: string;
  net_worth: { assets: number; liabilities: number; value: number; market_assets: number; other_assets: number; self_reported: number; unvalued: string[] };
  day_change: number;
  range: string;
  range_change: number | null;
  latest_price_date: string | null;
  unpriced: number;
  series: { points: { date: string; value: number; net_invested: number; benchmark?: number | null; missing?: number }[]; benchmark_label: string | null };
  allocation: { asset_class: string; value: number; share: number }[];
  returns: { invested: number; value: number; gain: number; xirr: number | null; simple: number | null; note: string | null };
  movers: { instrument: Instrument; day_change_pct: number; day_change: number; price_date: string }[];
  health: HealthCheck | null;
  profile_version: number | null;
  advice: { id: string; title: string; status: string; suggested_at: string }[];
  holdings_count: number;
};

/** GET /api/home. Every amount, share, offset and date is computed by the API (finadvisor/advisor/overview.py). */
export type CashFlow = {
  take_home: number;
  emis: number;
  expenses: number;
  left_over: number;
  short_by: number;
  widths: { emis: number; expenses: number; left_over: number } | null;
  /** Monthly total of the SIPs found from purchases; it is part of the left-over, not on top of it. */
  sips?: number;
  sips_count?: number;
};

export type TimelineStep = {
  order: number;
  action: string;
  text: string;
  rule: string | null;
  kind: "dated" | "ongoing" | "one_off";
  goal: string | null;
  monthly: number;
  months: number;
  start_month: number;
  end_month: number | null;
  starts_on: string;
  ends_on: string | null;
  recommendation_id: string | null;
  status: "suggested" | "pending" | "done" | "skipped";
  offset: number;
  width: number;
};

export type HomePlan = {
  steps: TimelineStep[];
  total: number;
  done: number;
  skipped: number;
  next_order: number | null;
  horizon_months: number;
  axis: { month: number; label_on: string; offset: number }[];
  monthly_surplus: number;
  investing_monthly: number;
  invest_start_month: number;
  invest_starts_on: string;
  notes: string[];
  advice_run_id: string;
  chat_id: string | null;
  made_at: string;
  profile_version: number | null;
  audit_status: string | null;
  stale: boolean;
};

export type GoalProgress = {
  goal_id: string;
  name: string;
  target_today: number;
  saved_so_far: number;
  funded: number;
  horizon_years: number;
  target_future: number | null;
  sip_needed: number | null;
  monthly_assigned: number | null;
  fundable: boolean | null;
  shortfall: number;
};

export type HomeResp = {
  profile_version: number | null;
  cash_flow: CashFlow | null;
  health: HealthCheck | null;
  health_history: { at: string; score: number; out_of: number; profile_version: number | null }[];
  plan: HomePlan | null;
  goals: GoalProgress[];
};

/** A SIP found from purchases (finadvisor/portfolio/sips.py). `off` = the person marked it stopped. */
export type SipRow = {
  id: string;
  instrument: Instrument;
  amount: number;
  day_of_month: number;
  since: string;
  instalments: number;
  last_date: string;
  next_expected: string;
  status: "active" | "missed" | "stopped" | "off";
  active: boolean;
};
export type SipsResp = { items: SipRow[]; monthly_total: number; as_of: string; window: { grace_days: number; tolerance: number; min_instalments: number } };

/** One of the four in-app reminders. `tab` is the My money tab it opens; without it, Home. */
export type Nudge = { id: string; kind: "prices_stale" | "step_due" | "profile_old" | "sip_missed"; title: string; body: string; to: string; tab: string | null };

export type GainsStatement = {
  financial_year: string;
  from: string;
  to: string;
  years: string[];
  rows: {
    instrument_id: string; name: string; kind: string; tax_class: "equity" | "slab"; buy_date: string; sell_date: string;
    quantity: number; buy_price: number; sell_price: number; cost: number; proceeds: number; gain: number; term: "long" | "short";
  }[];
  equity: {
    long_term: number; short_term: number; exemption: number; taxable_long_term: number; long_term_tax: number;
    short_term_tax: number; tax: number; long_term_rate: number; short_term_rate: number;
  };
  slab: { gain: number };
  rates_of: string;
  note: string;
};
