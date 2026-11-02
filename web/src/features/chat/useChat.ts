import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { api } from "@/lib/api";
import type { Card, ChatSummary, Message, Source, Stage, Why } from "@/lib/types";

type ChatDetail = ChatSummary & { messages: Message[]; generating: boolean };

export type LiveMessage = Message & { why?: Why };

export function useChatList(q: string) {
  return useQuery({ queryKey: ["chats", q], queryFn: () => api.get<ChatSummary[]>(`/api/chats${q ? `?q=${encodeURIComponent(q)}` : ""}`) });
}

/*
 * Live (streaming) state lives outside React, keyed by chat id ("new" before the chat exists). `/chat` and
 * `/chat/$chatId` are separate routes, so sending the first message remounts the page; keeping the stream here means
 * the new page shows the question and the answer as it arrives instead of the empty start screen.
 */
type LiveState = { messages: LiveMessage[]; busy: boolean; error: string | null };
const EMPTY: LiveState = { messages: [], busy: false, error: null };
const store = new Map<string, LiveState>();
const aborts = new Map<string, AbortController>();
const whyById: Record<string, Why> = {};
const subs = new Set<() => void>();
const notify = () => subs.forEach((f) => f());
const subscribe = (f: () => void) => {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
};
function patch(key: string, fn: (s: LiveState) => LiveState) {
  store.set(key, fn(store.get(key) ?? EMPTY));
  notify();
}
function rename(from: string, to: string) {
  const s = store.get(from);
  if (!s) return;
  store.delete(from);
  store.set(to, s);
  notify();
}
const updateDraft = (key: string, fn: (m: LiveMessage) => LiveMessage) =>
  patch(key, (s) => ({ ...s, messages: s.messages.map((m) => (m.id === "live-assistant" ? fn(m) : m)) }));

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Reveals streamed text at a steady pace. The server sends whole sentences (each is checked before it is shown),
 * which reads as jumps; this spreads them over animation frames, speeding up when a backlog builds.
 */
function typewriter(onText: (t: string) => void) {
  let pending = "";
  let raf: number | null = null;
  const tick = () => {
    raf = null;
    if (!pending) return;
    const n = Math.max(2, Math.ceil(pending.length / 12));
    onText(pending.slice(0, n));
    pending = pending.slice(n);
    if (pending) raf = requestAnimationFrame(tick);
  };
  return {
    push(t: string) {
      if (reducedMotion()) return onText(t);
      pending += t;
      if (raf === null) raf = requestAnimationFrame(tick);
    },
    flush() {
      if (raf !== null) cancelAnimationFrame(raf);
      raf = null;
      if (pending) onText(pending);
      pending = "";
    },
  };
}

export function useChat(chatId: string | undefined) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const key = chatId ?? "new";
  const detail = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => api.get<ChatDetail>(`/api/chats/${chatId}`),
    enabled: !!chatId,
  });
  const live = useSyncExternalStore(subscribe, () => store.get(key) ?? EMPTY);

  const messages: LiveMessage[] = useMemo(() => {
    const saved = (detail.data?.messages ?? []).map((m) => (whyById[m.id] ? { ...m, why: whyById[m.id] } : m));
    return live.messages.length ? [...saved, ...live.messages] : saved;
  }, [detail.data, live.messages]);

  const run = useCallback(
    async (path: string, body: unknown, target: string) => {
      const ctrl = new AbortController();
      aborts.set(target, ctrl);
      const typer = typewriter((t) => updateDraft(target, (m) => ({ ...m, content: m.content + t })));
      let why: Why | undefined;
      try {
        await api.stream(
          path,
          body,
          (ev, data) => {
            if (ev === "route") updateDraft(target, (m) => ({ ...m, route: data.route }));
            else if (ev === "stage") updateDraft(target, (m) => ({ ...m, stages: upsertStage(m.stages ?? [], data as Stage) }));
            else if (ev === "card") updateDraft(target, (m) => ({ ...m, cards: [...m.cards, data as Card] }));
            else if (ev === "token") typer.push(data.text);
            else if (ev === "sources") updateDraft(target, (m) => ({ ...m, sources: data.sources as Source[] }));
            else if (ev === "why") {
              why = data as Why;
              updateDraft(target, (m) => ({ ...m, why }));
            } else if (ev === "done") {
              if (why) whyById[data.message_id] = why;
              typer.flush();
              updateDraft(target, (m) => ({ ...m, status: data.status }));
            } else if (ev === "error") patch(target, (s) => ({ ...s, error: data.message }));
          },
          ctrl.signal,
        );
      } catch (e) {
        if ((e as Error).name !== "AbortError") patch(target, (s) => ({ ...s, error: (e as Error).message || "Connection lost." }));
      } finally {
        typer.flush();
        aborts.delete(target);
        await Promise.all([
          qc.invalidateQueries({ queryKey: ["chat", target] }),
          qc.invalidateQueries({ queryKey: ["chats"] }),
          qc.invalidateQueries({ queryKey: ["profile"] }),
          qc.invalidateQueries({ queryKey: ["recommendations"] }),
          qc.invalidateQueries({ queryKey: ["dashboard"] }),
        ]);
        // the saved messages have been refetched, so the live copies can go (keep an error visible)
        patch(target, (s) => ({ messages: [], busy: false, error: s.error }));
      }
    },
    [qc],
  );

  const start = (target: string, userText: string | null) => {
    const now = new Date().toISOString();
    const draft: LiveMessage = {
      id: "live-assistant", role: "assistant", content: "", route: null, cards: [], sources: [], status: "streaming",
      advice_run_id: null, created_at: now, feedback: null, stages: [],
    };
    const user: LiveMessage | null = userText ? { ...draft, id: "live-user", role: "user", content: userText, status: "complete", stages: undefined } : null;
    // shown immediately, before any network round trip
    patch(target, () => ({ messages: user ? [user, draft] : [draft], busy: true, error: null }));
  };

  const send = useCallback(
    async (text: string, route?: "learn" | "plan" | "check") => {
      let target = key;
      start(target, text);
      if (!chatId) {
        try {
          const c = await api.post<ChatSummary>("/api/chats", {});
          rename("new", c.id);
          target = c.id;
          qc.setQueryData(["chat", c.id], { ...c, messages: [], generating: false });
          navigate({ to: "/chat/$chatId", params: { chatId: c.id }, replace: true });
        } catch (e) {
          patch(target, () => ({ messages: [], busy: false, error: (e as Error).message }));
          return;
        }
      }
      await run(`/api/chats/${target}/messages`, { text, route }, target);
    },
    [chatId, key, navigate, qc, run],
  );

  const regenerate = useCallback(async () => {
    if (!chatId) return;
    qc.setQueryData<ChatDetail>(["chat", chatId], (d) => {
      if (!d) return d;
      const last = [...d.messages].reverse().findIndex((m) => m.role === "assistant");
      if (last < 0) return d;
      return { ...d, messages: d.messages.slice(0, d.messages.length - 1 - last) };
    });
    start(chatId, null);
    await run(`/api/chats/${chatId}/regenerate`, {}, chatId);
  }, [chatId, qc, run]);

  const stop = useCallback(() => {
    aborts.get(key)?.abort();
    if (chatId) api.post(`/api/chats/${chatId}/stop`).catch(() => {});
  }, [chatId, key]);

  return { detail, messages, busy: live.busy, error: live.error, send, regenerate, stop };
}

function upsertStage(stages: Stage[], s: Stage): Stage[] {
  const i = stages.findIndex((x) => x.stage === s.stage);
  if (i < 0) return [...stages, s];
  const copy = stages.slice();
  copy[i] = { ...copy[i], ...s };
  return copy;
}
