// Shapes returned by the API (finadvisor/api). Cards are built server-side from computed results.

export type ChatSummary = { id: string; title: string; pinned: boolean; created_at: string; updated_at: string };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  route: "learn" | "plan" | "check" | "chat" | null;
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

/** "main" cards sit in the reply; "details" cards (full plan, goals, health check, what-if) open on request. */
export type Card = (HealthCheck | PlanCard | GoalCard | NotYetCard | WhatIfCard | ProfileCardT | QuestionnaireCard | EvidenceCard | FollowupsCard) & {
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
