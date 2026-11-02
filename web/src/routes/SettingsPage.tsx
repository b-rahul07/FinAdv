import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { NOT_ADVISER, PageHeader, Section, Skeleton } from "@/components/common";
import { useMe } from "@/components/layout/AppShell";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, inr, setIndianGrouping } from "@/lib/format";

type Upload = { id: string; filename: string; file_type: string; cas_type: string; period_from: string | null; period_to: string | null; status: string; counts: Record<string, any>; created_at: string };
type Session = { id: string; user_agent: string | null; created_at: string; last_seen_at: string; current: boolean };
type About = { version: string; notice: string; model: Record<string, any>; configs: Record<string, string>; stored: { what: string; why: string }[]; never_stored: string[] };

export function SettingsPage() {
  const me = useMe();
  const qc = useQueryClient();
  const auth = useAuth();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/me/sessions") });
  const about = useQuery({ queryKey: ["about"], queryFn: () => api.get<About>("/api/about") });
  const uploads = useQuery({ queryKey: ["cas"], queryFn: () => api.get<Upload[]>("/api/cas") });
  const delUpload = useMutation({
    mutationFn: (id: string) => api.del(`/api/cas/${id}`),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Statement and its imported transactions deleted");
    },
  });
  const [name, setName] = useState<string | null>(null);

  const putSettings = useMutation({
    mutationFn: (b: Record<string, unknown>) => api.put("/api/settings", b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const research = useMutation({
    mutationFn: (opt_in: boolean) => api.put("/api/settings/research", { opt_in }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["me"] });
      toast.success(v ? "Thank you for joining the study" : "You have left the study; no new usage data will be recorded");
    },
  });
  const saveName = useMutation({
    mutationFn: (n: string) => api.patch("/api/me", { name: n }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      toast.success("Saved");
    },
  });
  const delAccount = useMutation({
    mutationFn: () => api.del("/api/me"),
    onSuccess: () => {
      toast.success("Your account and all its data were deleted");
      auth.signOut();
    },
  });

  if (!me.data) return <div className="mx-auto max-w-3xl p-8"><Skeleton className="h-64" /></div>;
  const s = me.data.settings;
  const row = "flex flex-wrap items-center justify-between gap-4 py-4";

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 md:px-8 md:py-10">
      <PageHeader eyebrow="Account and preferences" title="Settings" />
      <div className="space-y-4">
        <Section eyebrow="Account" title={me.data.email}>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              saveName.mutate(name ?? me.data.name ?? "");
            }}
          >
            <label className="flex-1 text-sm font-medium">
              Name
              <input className="mt-1 w-full rounded-xl border bg-card px-3 py-2.5" value={name ?? me.data.name ?? ""} onChange={(e) => setName(e.target.value)} />
            </label>
            <button className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">Save</button>
          </form>
          <p className="mt-3 text-xs text-muted-foreground">Signed in with {me.data.provider === "dev" ? "a development session" : me.data.provider}.</p>
        </Section>

        <Section eyebrow="Appearance" title="Theme">
          <ThemeToggle />
        </Section>

        <Section eyebrow="Numbers" title="Digit grouping">
          <div className={row}>
            <div>
              <p className="text-sm font-medium">Indian grouping</p>
              <p className="num whitespace-normal text-sm text-muted-foreground">
                {s.indian_grouping ? "₹1,23,45,678" : "₹12,345,678"} · amounts in rupees · dates in IST
              </p>
            </div>
            <Switch
              checked={s.indian_grouping}
              aria-label="Indian digit grouping"
              onCheckedChange={(v) => {
                setIndianGrouping(v);
                putSettings.mutate({ indian_grouping: v });
              }}
            />
          </div>
        </Section>

        <Section eyebrow="Notifications" title="In-app only">
          {[
            ["data_refresh", "Problems refreshing prices or NAVs"],
            ["plan_reminders", "Reminders about plan steps"],
          ].map(([k, label]) => (
            <div key={k} className={row}>
              <p className="text-sm">{label}</p>
              <Switch checked={!!s.notifications[k]} aria-label={label} onCheckedChange={(v) => putSettings.mutate({ notifications: { ...s.notifications, [k]: v } })} />
            </div>
          ))}
        </Section>

        <Section eyebrow="Security" title="Active sessions">
          <ul className="divide-y">
            {(sessions.data ?? []).map((x) => (
              <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <div>
                  <p className="font-medium">{browser(x.user_agent)}{x.current && <span className="ml-2 rounded-full bg-info-soft px-2 py-0.5 text-xs font-bold">This device</span>}</p>
                  <p className="text-xs text-muted-foreground">Last active {dateTime(x.last_seen_at)}</p>
                </div>
                {!x.current && (
                  <button className="text-sm font-semibold text-loss" onClick={() => api.del(`/api/me/sessions/${x.id}`).then(() => sessions.refetch())}>
                    Sign out
                  </button>
                )}
              </li>
            ))}
          </ul>
          <button className="mt-3 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2" onClick={() => auth.signOut(true)}>
            Sign out of all devices
          </button>
        </Section>

        <Section eyebrow="Research participation" title="Help our study (optional)">
          <p className="text-sm text-muted-foreground">
            If you opt in, FinAdvisor records which features you use and how long tasks take, and may include an anonymised copy of your
            profile and advice records in our research data. Names, emails, statement passwords and account numbers are never included. You
            can leave at any time; it is off by default.
          </p>
          <div className={row}>
            <p className="text-sm font-medium">Use my anonymised data for research</p>
            <Switch checked={s.research_opt_in} aria-label="Research participation" onCheckedChange={(v) => research.mutate(v)} />
          </div>
        </Section>

        <Section eyebrow="Statements" title="Uploaded CAS files">
          {uploads.data?.length ? (
            <ul className="divide-y">
              {uploads.data.map((u) => (
                <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <div>
                    <p className="font-medium">{u.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {u.file_type} · {u.period_to ? `${u.period_from} to ${u.period_to} · ` : ""}{u.status === "imported" ? `${u.counts.transactions_added ?? 0} transactions imported` : "previewed, not imported"} · uploaded {dateTime(u.created_at)}
                    </p>
                  </div>
                  <button className="text-sm font-semibold text-loss" onClick={() => delUpload.mutate(u.id)}>Delete</button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No statements uploaded. Import one from Holdings.</p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">Deleting a statement also deletes the transactions imported from it. PDFs and passwords are never stored.</p>
        </Section>

        <Section eyebrow="Privacy and data" title="Your data">
          {about.data && (
            <>
              <h3 className="mb-2 text-sm font-bold">What FinAdvisor stores and why</h3>
              <ul className="mb-4 space-y-1.5 text-sm">
                {about.data.stored.map((x) => (
                  <li key={x.what}>
                    <strong>{x.what}:</strong> <span className="text-muted-foreground">{x.why}</span>
                  </li>
                ))}
              </ul>
              <p className="mb-4 text-sm">
                <strong>Never stored:</strong> <span className="text-muted-foreground">{about.data.never_stored.join("; ")}.</span>
              </p>
              <p className="mb-4 text-sm text-muted-foreground">
                Your chats are answered by an open-weight model FinAdvisor runs itself ({about.data.model.model}); your financial data is never sent to a third-party AI service.
              </p>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            <button className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2" onClick={() => api.download("/api/me/export", "finadvisor-export.json")}>
              Export all my data (JSON)
            </button>
            <AlertDialog>
              <AlertDialogTrigger className="rounded-full border border-loss/40 px-4 py-2 text-sm font-semibold text-loss hover:bg-loss-soft">Delete my account</AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete your account and all data?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently deletes your profile, chats, advice records, holdings and settings. It cannot be undone. Export your data first if you want a copy.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => delAccount.mutate()}>Delete everything</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </Section>

        <Section eyebrow="About" title={`FinAdvisor ${about.data?.version ?? ""}`}>
          <p className="text-sm">{NOT_ADVISER}</p>
          <h3 className="mb-1 mt-4 text-sm font-bold">Data sources</h3>
          <ul className="space-y-1 text-sm text-muted-foreground">
            <li>Mutual fund NAVs: AMFI daily NAV file; history from MFapi.in</li>
            <li>Stock prices: NSE and BSE end-of-day bhavcopy; corporate actions from the exchanges</li>
            <li>Benchmark: NSE Indices (Nifty 50 Total Return Index)</li>
            <li>Health-check thresholds: SEBI investor portal Financial Health Check</li>
            <li>Risk questionnaire: Grable &amp; Lytton (1999), via Kuzniak et al. (2015), CC BY-NC 4.0</li>
          </ul>
          {about.data && <p className="mt-4 text-xs text-muted-foreground">Rules {about.data.configs.rules} · shelf {about.data.configs.shelf} · tax {about.data.configs.tax} · config {about.data.configs.fingerprint} · example amount {inr(123456789)}</p>}
        </Section>
      </div>
    </div>
  );
}

function browser(ua: string | null) {
  if (!ua) return "Unknown device";
  const b = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${b} on ${os}` : b;
}
