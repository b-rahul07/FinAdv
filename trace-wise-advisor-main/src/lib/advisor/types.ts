/**
 * Frontend Data Models & TypeScript Types
 * ==========================================
 * Defines the shared TypeScript interfaces mirroring the backend data contracts.
 * 
 * Key Types:
 *   - UserProfile: Fields capturing user risk, horizon, budget, and goals.
 *   - PROFILE_FIELDS: Metadata used to render the ProfileCard and edit forms.
 *   - RetrievedChunk: Source excerpt and citation used in EvidencePanel.
 *   - RecommendationResponse: Advice payload containing text, allocations, and evidence.
 *   - ThreadItem: Discriminated union for rendering items in the chat stream
 *     (questions, text messages, profile cards, recommendation cards, errors).
 */

// User financial profile contract matching the Python UserProfile dataclass
export type UserProfile = {
  risk_tolerance: string;
  investment_horizon: string;
  goal_type: string;
  monthly_savings: string | number;
  existing_emi: string | number;
  bnpl_exposure: string;
  tax_saving_priority: string | number;
  financial_literacy: string;
};

// Form field definitions used by the ProfileCard component to render editable inputs
export const PROFILE_FIELDS: { key: keyof UserProfile; label: string; options?: string[] }[] = [
  {
    key: "risk_tolerance",
    label: "Risk tolerance",
    options: ["Conservative", "Moderate", "Aggressive"],
  },
  {
    key: "investment_horizon",
    label: "Investment horizon",
    options: ["Short-term (< 1 year)", "Medium-term (1–5 years)", "Long-term (> 5 years)"],
  },
  {
    key: "goal_type",
    label: "Goal type",
    options: ["Emergency fund", "Tax saving", "Wealth growth", "Retirement", "Child education", "Home purchase"],
  },
  { key: "monthly_savings", label: "Monthly savings (₹)" },
  { key: "existing_emi", label: "Existing EMI (₹)" },
  {
    key: "bnpl_exposure",
    label: "BNPL exposure",
    options: ["None", "Minor (< ₹10,000)", "Significant (₹10,000–50,000)", "Heavy (> ₹50,000)"],
  },
  {
    key: "tax_saving_priority",
    label: "Tax saving priority",
    options: ["1", "2", "3", "4", "5"],
  },
  {
    key: "financial_literacy",
    label: "Financial literacy",
    options: ["Beginner", "Intermediate", "Advanced"],
  },
];

// Document citation chunk representation for the UI
export type RetrievedChunk = {
  chunk_id: string;
  source_document: string;
  excerpt: string;
};

// Market news sentiment summary
export type SentimentSummary = {
  score: number;
  label: string;
  headlines_used: string[];
};

// Fired regulatory suitability rule
export type RuleFired = {
  rule_id: string;
  description: string;
};

// Verifiable audit record attached to recommendation
export type ProvenanceRecord = {
  model?: string;
  retrieval_k?: number;
  generated_at?: string;
  audit_constrained?: boolean;
  [key: string]: unknown;
};

// Complete recommendation payload returned from /api/session/{id}/recommend
export type RecommendationResponse = {
  recommendation_text: string;
  evidence: RetrievedChunk[];
  sentiment_summary?: SentimentSummary | undefined;
  rule_fired?: RuleFired | undefined;
  provenance?: ProvenanceRecord | undefined;
};

// Response from submitting a questionnaire answer
export type MessageResponse =
  | { type: "question"; question: string; options?: string[] | undefined; index?: number | undefined; total?: number | undefined }
  | { type: "profile_summary"; profile: UserProfile };

// Experimental ablation flag toggle state
export type AblationConfig = {
  enable_preference_confirmation: boolean;
  enable_audit_evidence: boolean;
};

// Database history message format
export type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  evidence?: RetrievedChunk[] | undefined;
  profile_snapshot?: UserProfile | undefined;
};

// ==============================================================================
// Client-Side Chat Thread Models
// ==============================================================================

// Discriminated union of items displayed in the interactive chat feed
export type ThreadItem =
  | { id: string; kind: "text"; role: "user" | "assistant"; content: string; timestamp: string }
  | {
      id: string;
      kind: "question";
      role: "assistant";
      content: string;
      options?: string[] | undefined;
      index?: number | undefined;
      total?: number | undefined;
      timestamp: string;
    }
  | {
      id: string;
      kind: "profile";
      role: "assistant";
      profile: UserProfile;
      confirmed: boolean;
      timestamp: string;
    }
  | {
      id: string;
      kind: "recommendation";
      role: "assistant";
      data: RecommendationResponse;
      timestamp: string;
    }
  | {
      id: string;
      kind: "error";
      role: "assistant";
      content: string;
      timestamp: string;
    };

// Session metadata shown in sidebar list
export type SessionSummary = {
  session_id: string;
  label: string;
  updated_at: string;
};

// Session data cached in browser localStorage
export type CachedSession = {
  session_id: string;
  label: string;
  updated_at: string;
  thread: ThreadItem[];
  stage: "elicitation" | "confirm" | "recommendation";
};

