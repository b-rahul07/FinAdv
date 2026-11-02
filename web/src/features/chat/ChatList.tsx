import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Pin, PinOff, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { dateGroup } from "@/lib/format";
import type { ChatSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useChatList } from "./useChat";

export function ChatList({ activeId, onNavigate }: { activeId?: string; onNavigate?: () => void }) {
  const [q, setQ] = useState("");
  const list = useChatList(q.trim());
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [deleting, setDeleting] = useState<ChatSummary | null>(null);

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ChatSummary> }) => api.patch(`/api/chats/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chats"] }),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/chats/${id}`),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["chats"] });
      toast.success("Chat deleted");
      if (id === activeId) navigate({ to: "/chat" });
    },
  });

  const chats = list.data ?? [];
  const pinned = chats.filter((c) => c.pinned);
  const groups = new Map<string, ChatSummary[]>();
  for (const c of chats.filter((c) => !c.pinned)) {
    const g = dateGroup(c.updated_at);
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  const sections: [string, ChatSummary[]][] = [...(pinned.length ? [["Pinned", pinned] as [string, ChatSummary[]]] : []), ...groups];

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 p-3">
        <Link
          to="/chat"
          onClick={onNavigate}
          className="flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Plus className="size-4" aria-hidden /> New chat
        </Link>
        <label className="flex items-center gap-2 rounded-full border bg-card px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-ring">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <span className="sr-only">Search chats</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" className="w-full bg-transparent outline-none" />
        </label>
      </div>
      <nav aria-label="Chats" className="flex-1 overflow-y-auto px-2 pb-4">
        {list.isLoading && (
          <div className="space-y-2 p-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-8" />
            ))}
          </div>
        )}
        {!list.isLoading && chats.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">{q ? "No chats match your search." : "Your chats will appear here."}</p>
        )}
        {sections.map(([label, items]) => (
          <div key={label} className="mb-3">
            <p className="px-3 pb-1 pt-2 text-xs font-semibold text-muted-foreground">{label}</p>
            <ul>
              {items.map((c) => (
                <li key={c.id} className="group relative">
                  {renaming === c.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        patch.mutate({ id: c.id, body: { title: name } });
                        setRenaming(null);
                      }}
                    >
                      <input
                        autoFocus
                        aria-label="Chat name"
                        className="w-full rounded-lg border bg-card px-3 py-2 text-sm"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onBlur={() => setRenaming(null)}
                        onKeyDown={(e) => e.key === "Escape" && setRenaming(null)}
                      />
                    </form>
                  ) : (
                    <Link
                      to="/chat/$chatId"
                      params={{ chatId: c.id }}
                      onClick={onNavigate}
                      aria-current={c.id === activeId ? "page" : undefined}
                      className={cn(
                        "block truncate rounded-lg py-2 pl-3 pr-9 text-sm transition-colors",
                        c.id === activeId ? "bg-surface-2 font-semibold" : "text-foreground/85 hover:bg-surface-2/70",
                      )}
                    >
                      {c.title}
                    </Link>
                  )}
                  {renaming !== c.id && (
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        aria-label={`Options for ${c.title}`}
                        className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-card focus:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
                      >
                        <MoreHorizontal className="size-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => {
                            setName(c.title);
                            setRenaming(c.id);
                          }}
                        >
                          <Pencil className="size-4" /> Rename
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => patch.mutate({ id: c.id, body: { pinned: !c.pinned } })}>
                          {c.pinned ? <PinOff className="size-4" /> : <Pin className="size-4" />} {c.pinned ? "Unpin" : "Pin"}
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-loss focus:text-loss" onSelect={() => setDeleting(c)}>
                          <Trash2 className="size-4" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>"{deleting?.title}" and its messages will be deleted. Advice records stay in your history.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting) del.mutate(deleting.id);
                setDeleting(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
