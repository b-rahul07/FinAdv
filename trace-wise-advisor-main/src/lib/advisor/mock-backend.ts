// Local stand-in for the Python/FastAPI backend so the UI is demoable before
// integration. Mirrors the §4 contract exactly; delete once the real API is up.

import type {
  AblationConfig,
  MessageResponse,
  RecommendationResponse,
  UserProfile,
} from "./types";

const QUESTIONS: { key: keyof UserProfile; question: string; options?: string[] }[] = [
  {
    key: "financial_literacy",
    question: "How would you rate your financial knowledge?",
    options: ["Beginner", "Intermediate", "Advanced"],
  },
  {
    key: "risk_tolerance",
    question: "How would you describe your risk tolerance?",
    options: ["Conservative", "Moderate", "Aggressive"],
  },
  {
    key: "investment_horizon",
    question: "What is your investment time horizon?",
    options: ["Short-term (< 1 year)", "Medium-term (1–5 years)", "Long-term (> 5 years)"],
  },
  {
    key: "goal_type",
    question: "What is the primary goal for this investment?",
    options: ["Emergency fund", "Tax saving", "Wealth growth", "Retirement", "Child education", "Home purchase"],
  },
  {
    key: "monthly_savings",
    question: "What is your approximate monthly savings capacity (in ₹)?",
  },
  {
    key: "existing_emi",
    question: "What is your total existing EMI burden per month (in ₹)?",
  },
  {
    key: "bnpl_exposure",
    question: "Do you have any active Buy Now Pay Later (BNPL) commitments?",
    options: ["None", "Minor (< ₹10,000)", "Significant (₹10,000–50,000)", "Heavy (> ₹50,000)"],
  },
  {
    key: "tax_saving_priority",
    question: "How important is tax saving (Section 80C, 80D, etc.) in your investment decision?",
    options: ["1", "2", "3", "4", "5"],
  },
];

type MockSession = { answers: string[] };

const sessions = new Map<string, MockSession>();

let ablation: AblationConfig = {
  enable_preference_confirmation: true,
  enable_audit_evidence: true,
};

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function normaliseRisk(answer: string): string {
  const a = answer.toLowerCase();
  if (a.includes("conservative")) return "Conservative";
  if (a.includes("aggressive")) return "Aggressive";
  return "Moderate";
}

function buildProfile(answers: string[]): UserProfile {
  return {
    financial_literacy: answers[0] ?? "Beginner",
    risk_tolerance: normaliseRisk(answers[1] ?? "Moderate"),
    investment_horizon: answers[2] ?? "Medium-term (1–5 years)",
    goal_type: answers[3] ?? "Wealth growth",
    monthly_savings: answers[4] ?? "15000",
    existing_emi: answers[5] ?? "9000",
    bnpl_exposure: answers[6] ?? "None",
    tax_saving_priority: answers[7] ?? "3",
  };
}

export const mockBackend = {
  async createSession() {
    await delay(200);
    const id = `demo-${Math.random().toString(36).slice(2, 9)}`;
    sessions.set(id, { answers: [] });
    return { session_id: id };
  },

  async firstQuestion(sessionId: string): Promise<MessageResponse> {
    sessions.set(sessionId, sessions.get(sessionId) ?? { answers: [] });
    await delay(250);
    const first = QUESTIONS[0]!;
    return {
      type: "question",
      question: first.question,
      options: first.options,
      index: 1,
      total: QUESTIONS.length,
    };
  },

  async sendMessage(sessionId: string, answer: string): Promise<MessageResponse> {
    const s = sessions.get(sessionId) ?? { answers: [] };
    s.answers.push(answer);
    sessions.set(sessionId, s);
    await delay(400);

    if (s.answers.length >= QUESTIONS.length) {
      return { type: "profile_summary", profile: buildProfile(s.answers) };
    }
    const q = QUESTIONS[s.answers.length]!;
    return {
      type: "question",
      question: q.question,
      options: q.options,
      index: s.answers.length + 1,
      total: QUESTIONS.length,
    };
  },

  async confirm(_sessionId: string, profile: UserProfile) {
    await delay(300);
    return { confirmed_profile: profile };
  },

  async recommend(sessionId: string): Promise<RecommendationResponse> {
    await delay(2600);
    const profile = buildProfile(sessions.get(sessionId)?.answers ?? []);
    const audit = ablation.enable_audit_evidence;

    const text = audit
      ? `Based on your ${profile.risk_tolerance.toLowerCase()} risk profile and a ${profile.investment_horizon} horizon, a staged approach looks most suitable for you.

Before investing further, your existing EMI and BNPL commitments deserve attention: they sit above the share of income generally considered comfortable, which reduces how much market volatility your budget can absorb [1].

For the portion you can invest, a mix weighted toward diversified index funds with a smaller allocation to debt instruments matches the suitability band your answers fall into [2]. Products carrying a higher risk-o-meter rating than your stated tolerance are not appropriate here [3].

Current market sentiment is mildly cautious, which is a reason to phase your entry over several months rather than to time it — not a prediction of direction [4].

This is educational guidance about suitability. It is not investment advice and no returns are guaranteed.`
      : `Based on your ${profile.risk_tolerance.toLowerCase()} risk profile and a ${profile.investment_horizon} horizon, a diversified index-weighted mix with a smaller debt allocation, entered in phases over several months, appears broadly suitable. Keep an eye on your existing EMI commitments before increasing contributions.

This is educational guidance about suitability. It is not investment advice and no returns are guaranteed.`;

    return {
      recommendation_text: text,
      evidence: audit
        ? [
            {
              chunk_id: "c-101",
              source_document: "RBI Household Indebtedness Report (2024)",
              excerpt:
                "Households with total EMI obligations exceeding 40% of net monthly income show materially reduced capacity to absorb income shocks and are advised to prioritise liability reduction over incremental market exposure.",
            },
            {
              chunk_id: "c-204",
              source_document: "SEBI Investor Suitability Guidelines",
              excerpt:
                "Suitability assessment must map the investor's stated risk tolerance and stated horizon to a defined product band; diversified equity index products fall within the moderate band for horizons of three years and above.",
            },
            {
              chunk_id: "c-311",
              source_document: "SEBI Risk-o-meter Circular",
              excerpt:
                "Schemes labelled 'Very High' on the risk-o-meter shall not be presented as suitable to investors whose recorded risk profile is conservative or moderate.",
            },
            {
              chunk_id: "c-478",
              source_document: "Market Sentiment Digest — last 7 days",
              excerpt:
                "Aggregate tone across 42 indexed headlines is mildly negative, driven by rate-path uncertainty. Sentiment signals are used for phasing guidance only and are not forecasts.",
            },
          ]
        : [],
      sentiment_summary: audit
        ? {
            score: -0.18,
            label: "Mildly cautious",
            headlines_used: [
              "Rate path uncertainty keeps benchmark indices range-bound",
              "Domestic inflows steady despite global volatility",
              "Analysts flag stretched valuations in mid-cap segment",
            ],
          }
        : undefined,
      rule_fired: audit
        ? {
            rule_id: "R-EMI-01",
            description:
              "Your EMI-to-income ratio exceeds the recommended threshold, so debt reduction is prioritised ahead of increased market exposure.",
          }
        : undefined,
      provenance: {
        model: "local-llm (demo)",
        retrieval_k: 4,
        generated_at: new Date().toISOString(),
        audit_constrained: audit,
        preference_confirmation: ablation.enable_preference_confirmation,
      },
    };
  },

  async getAblation() {
    return ablation;
  },

  async setAblation(config: AblationConfig) {
    ablation = config;
    return ablation;
  },
};

export const MOCK_QUESTION_COUNT = QUESTIONS.length;
