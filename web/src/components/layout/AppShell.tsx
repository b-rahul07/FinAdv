import { Link, Navigate, Outlet, useRouterState } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Home, LogOut, MessageCircle, Settings, Wallet } from "lucide-react";
import { useEffect } from "react";
import { Nudges } from "@/components/layout/Nudges";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { setIndianGrouping } from "@/lib/format";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

// Four places, the same on a phone and a desktop. `also` lists paths that belong to a tab without sharing its prefix.
const NAV = [
  { to: "/", label: "Home", icon: Home, exact: true },
  { to: "/chat", label: "Advisor", icon: MessageCircle },
  { to: "/money", label: "My money", icon: Wallet, also: ["/holdings"] },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function useMe() {
  const { signedIn } = useAuth();
  return useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/me"), enabled: signedIn });
}

export function AppShell() {
  const auth = useAuth();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const me = useMe();

  useEffect(() => {
    if (me.data) setIndianGrouping(me.data.settings.indian_grouping);
  }, [me.data]);

  if (!auth.ready) return null;
  if (!auth.signedIn) return <Navigate to="/signin" />;

  const under = (to: string) => path === to || path.startsWith(to + "/");
  const active = (n: (typeof NAV)[number]) => ("exact" in n ? path === n.to : under(n.to) || ("also" in n && n.also.some(under)));
  const isChat = path.startsWith("/chat");

  return (
    <div className="min-h-dvh bg-background">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-card focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[76px] flex-col border-r bg-surface md:flex xl:w-60" aria-label="Main">
        <div className="flex h-16 items-center gap-2 px-5">
          <Logo />
        </div>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV.map((n) => {
            const { to, label, icon: Icon } = n;
            const on = active(n);
            return (
              <Link
                key={to}
                to={to}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  on ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2/70 hover:text-foreground",
                )}
              >
                <Icon className="size-5 shrink-0" aria-hidden />
                <span className="hidden xl:inline">{label}</span>
                <span className="sr-only xl:hidden">{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="space-y-2 border-t p-3">
          <Nudges />
          <ThemeToggle compact />
          <button
            onClick={() => auth.signOut()}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            <LogOut className="size-5" aria-hidden />
            <span className="hidden xl:inline">Sign out</span>
            <span className="sr-only xl:hidden">Sign out</span>
          </button>
        </div>
      </aside>

      <main id="main" className={cn("md:pl-[76px] xl:pl-60", isChat ? "" : "pb-28 md:pb-10")}>
        {me.data?.is_demo && (
          <div role="note" className="bg-warn-soft px-4 py-2 text-center text-xs font-semibold">
            Example data · this is a demo account with a fictional person; prices are real
          </div>
        )}
        {!isChat && <Nudges floating />}
        <Outlet />
      </main>

      {!isChat && (
        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-4 z-40 mx-auto flex w-[min(92vw,380px)] justify-between rounded-full border bg-card/90 p-1.5 shadow-lg backdrop-blur md:hidden"
        >
          {NAV.map((n) => {
            const { to, label, icon: Icon } = n;
            const on = active(n);
            return (
              <Link
                key={to}
                to={to}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "flex flex-1 flex-col items-center gap-0.5 rounded-full px-2 py-1.5 text-[11px] font-semibold transition-colors",
                  on ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                )}
              >
                <Icon className="size-5" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
