import { useParams } from "@tanstack/react-router";
import { ArrowUp, PanelLeft, Square } from "lucide-react";
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ErrorState } from "@/components/common";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ChatList } from "@/features/chat/ChatList";
import { MessageView } from "@/features/chat/MessageView";
import { useChat } from "@/features/chat/useChat";

const STARTERS = [
  { title: "Make me a money plan", body: "for my salary and goals", text: "Make me a money plan for my salary and goals" },
  { title: "Do I have enough", body: "emergency savings?", text: "Do I have enough emergency savings?" },
  { title: "Should I buy a phone", body: "on a no-cost EMI?", text: "Should I buy a phone on a no-cost EMI?" },
  { title: "Explain ELSS", body: "and how Section 80C works", text: "What is ELSS and how does Section 80C work?" },
  { title: "Is F&O trading", body: "right for me?", text: "Is F&O trading right for me?" },
  { title: "How much should I save", body: "for retirement?", text: "How much should I save for retirement?" },
];

export function ChatPage() {
  const params = useParams({ strict: false }) as { chatId?: string };
  const chatId = params.chatId;
  const { detail, messages, busy, error, send, regenerate, stop } = useChat(chatId);
  const [drawer, setDrawer] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true); // follow new text only while the reader is at the bottom

  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  const last = messages.at(-1);
  const contentKey = `${messages.length}:${last?.content.length ?? 0}:${last?.cards.length ?? 0}:${last?.stages?.length ?? 0}`;
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight; // instant: smooth scrolling on every token reads as lag
  }, [contentKey]);

  useEffect(() => {
    stick.current = true;
  }, [chatId]);

  const ask = useCallback(
    (t: string) => {
      const v = t.trim();
      if (!v || busy) return;
      stick.current = true;
      send(v);
    },
    [busy, send],
  );

  const empty = messages.length === 0 && (!chatId || !!detail.data);
  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  return (
    <div className="flex h-dvh">
      <aside className="hidden w-72 shrink-0 border-r bg-surface lg:block" aria-label="Chat history">
        <ChatList activeId={chatId} />
      </aside>
      <Dialog open={drawer} onOpenChange={setDrawer}>
        <DialogContent className="left-0 top-0 h-dvh max-w-[85vw] translate-x-0 translate-y-0 rounded-none p-0 sm:max-w-sm">
          <DialogTitle className="sr-only">Chat history</DialogTitle>
          <ChatList activeId={chatId} onNavigate={() => setDrawer(false)} />
        </DialogContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-2 border-b px-3 lg:px-6">
          <button className="rounded-lg p-2 hover:bg-surface-2 lg:hidden" aria-label="Open chat history" onClick={() => setDrawer(true)}>
            <PanelLeft className="size-5" />
          </button>
          <h1 className="truncate text-sm font-semibold">{detail.data?.title ?? "New chat"}</h1>
        </header>

        <div ref={scroller} onScroll={onScroll} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
            {detail.isError && <ErrorState message="This chat could not be loaded." onRetry={() => detail.refetch()} />}
            {chatId && detail.isLoading && messages.length === 0 && (
              <div className="space-y-3">
                <div className="skeleton ml-auto h-10 w-1/2" />
                <div className="skeleton h-24" />
              </div>
            )}
            {empty && !detail.isLoading && <Starters onPick={ask} />}
            <div className="space-y-8">
              {messages.map((m) => (
                <MessageView key={m.id} m={m} isLast={m.id === lastAssistantId} onRegenerate={regenerate} onAsk={ask} />
              ))}
            </div>
            {error && (
              <div className="mt-4">
                <ErrorState message={error} onRetry={lastAssistantId ? regenerate : undefined} />
              </div>
            )}
          </div>
        </div>

        <Composer busy={busy} onSend={ask} onStop={stop} focusKey={chatId} />
      </div>
    </div>
  );
}

const Starters = memo(function Starters({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="pt-[8vh]">
      <p className="eyebrow">FinAdvisor advisor</p>
      <h2 className="mt-2 text-3xl font-extrabold tracking-tight md:text-4xl">What would you like to work out?</h2>
      <p className="mt-2 max-w-xl text-muted-foreground">
        Ask a general question, check whether something suits you, or get a plan built from your confirmed profile.
      </p>
      <div className="mt-8 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {STARTERS.map((s) => (
          <button key={s.text} onClick={() => onPick(s.text)} className="card px-4 py-3.5 text-left transition-colors hover:bg-surface-2">
            <span className="block text-sm font-semibold">{s.title}</span>
            <span className="block text-sm text-muted-foreground">{s.body}</span>
          </button>
        ))}
      </div>
    </div>
  );
});

/** Owns its own text state, so typing never re-renders the conversation above it. */
const Composer = memo(function Composer({ busy, onSend, onStop, focusKey }: { busy: boolean; onSend: (t: string) => void; onStop: () => void; focusKey?: string }) {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    box.current?.focus();
  }, [focusKey]);
  const submit = () => {
    const v = text.trim();
    if (!v || busy) return;
    setText("");
    onSend(v);
  };
  return (
    <div className="border-t bg-background/80 px-3 pb-[max(env(safe-area-inset-bottom),12px)] pt-3 backdrop-blur md:px-6">
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="composer" className="sr-only">
          Message FinAdvisor
        </label>
        <textarea
          id="composer"
          ref={box}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about your money…"
          className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 outline-none [field-sizing:content]"
        />
        {busy ? (
          <button type="button" onClick={onStop} className="grid size-10 place-items-center rounded-full bg-primary text-primary-foreground" aria-label="Stop generating">
            <Square className="size-4 fill-current" />
          </button>
        ) : (
          <button type="submit" disabled={!text.trim()} className="grid size-10 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-40" aria-label="Send">
            <ArrowUp className="size-5" />
          </button>
        )}
      </form>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground">
        Education and planning only, not investment advice. FinAdvisor is not SEBI-registered and never recommends individual securities.
      </p>
    </div>
  );
});
