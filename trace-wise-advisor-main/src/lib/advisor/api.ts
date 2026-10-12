/**
 * Frontend Advisory API Client
 * =============================
 * This module connects the React user interface to the Python FastAPI backend.
 * 
 * Features:
 *   - Base URL configuration from environment (VITE_ADVISOR_API_URL).
 *   - Graceful offline fallback: If the Python backend is temporarily offline,
 *     it automatically falls back to an in-browser mock backend so the user
 *     interface never freezes or crashes.
 *   - Type-safe HTTP requests for session creation, questionnaire chatting,
 *     profile confirmation, and financial recommendation generation.
 */

import { mockBackend } from "./mock-backend";
import type {
  AblationConfig,
  HistoryMessage,
  MessageResponse,
  RecommendationResponse,
  UserProfile,
} from "./types";

// Base URL of the FastAPI backend (e.g., http://127.0.0.1:8000)
const BASE_URL = ((import.meta.env as Record<string, string | undefined>)[
  "VITE_ADVISOR_API_URL"
] ?? "").replace(/\/$/, "");

// Check if live backend URL is configured
export const isLiveBackend = () => BASE_URL.length > 0;

let liveFailed = false;
export const backendUnreachable = () => liveFailed;

/**
 * Low-level HTTP fetch helper with JSON serialization and HTTP error checking.
 */
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`Backend responded ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

/**
 * Resilient wrapper: tries to execute against the live Python backend,
 * but falls back to mockBackend if the network request fails.
 */
async function withFallback<T>(live: () => Promise<T>, mock: () => Promise<T>): Promise<T> {
  if (!isLiveBackend()) return mock();
  try {
    const result = await live();
    liveFailed = false;
    return result;
  } catch (err) {
    liveFailed = true;
    console.warn("Live backend failed, falling back to mock implementation:", err);
    return await mock();
  }
}

/**
 * API service object exposing all advisor operations to UI components.
 */
export const advisorApi = {
  // 1. Create a brand-new chat session
  createSession: () =>
    withFallback(
      () => call<{ session_id: string }>("/api/session", { method: "POST" }),
      () => mockBackend.createSession(),
    ),

  // 2. Start the questionnaire: sending an empty answer prompts the backend for Question 1
  start: (sessionId: string) =>
    withFallback(
      () =>
        call<MessageResponse>(`/api/session/${sessionId}/message`, {
          method: "POST",
          body: JSON.stringify({ answer: "" }),
        }),
      () => mockBackend.firstQuestion(sessionId),
    ),

  // 3. Submit user's answer to the current profiling question
  sendMessage: (sessionId: string, answer: string) =>
    withFallback(
      () =>
        call<MessageResponse>(`/api/session/${sessionId}/message`, {
          method: "POST",
          body: JSON.stringify({ answer }),
        }),
      () => mockBackend.sendMessage(sessionId, answer),
    ),

  // 4. Confirm or update the elicited user profile
  confirm: (sessionId: string, profile: UserProfile) =>
    withFallback(
      () =>
        call<{ confirmed_profile: UserProfile }>(`/api/session/${sessionId}/confirm`, {
          method: "POST",
          body: JSON.stringify({ profile }),
        }),
      () => mockBackend.confirm(sessionId, profile),
    ),

  // 5. Trigger multi-agent pipeline and generate verified recommendation
  recommend: (sessionId: string) =>
    withFallback(
      () =>
        call<RecommendationResponse>(`/api/session/${sessionId}/recommend`, {
          method: "POST",
        }),
      () => mockBackend.recommend(sessionId),
    ),

  // 6. Fetch previous chat message history for the session
  history: (sessionId: string) =>
    withFallback(
      () => call<{ messages: HistoryMessage[] }>(`/api/session/${sessionId}/history`),
      async () => ({ messages: [] as HistoryMessage[] }),
    ),

  // 7. Get experimental ablation toggle status
  getAblation: () =>
    withFallback(
      () => call<AblationConfig>("/api/config/ablation"),
      () => mockBackend.getAblation(),
    ),

  // 8. Update experimental ablation flags
  setAblation: (config: AblationConfig) =>
    withFallback(
      () =>
        call<AblationConfig>("/api/config/ablation", {
          method: "POST",
          body: JSON.stringify(config),
        }),
      () => mockBackend.setAblation(config),
    ),
};

