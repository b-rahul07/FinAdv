import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, configureApi } from "./api";

// Supabase Auth when configured (email + Google). Without it, a local development sign-in is used;
// the API refuses development tokens in production.
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const supabase: SupabaseClient | null =
  SUPABASE_URL && SUPABASE_ANON_KEY ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;
export const authMode: "supabase" | "dev" = supabase ? "supabase" : "dev";

const DEV_KEY = "fa-dev-token";

type AuthState = {
  ready: boolean;
  signedIn: boolean;
  email: string | null;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (email: string, password: string, name: string) => Promise<string | null>;
  signInWithGoogle: () => Promise<void>;
  devSignIn: (email: string, name?: string) => Promise<void>;
  signOut: (everywhere?: boolean) => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

// The current access token, readable synchronously so the very first request already carries it.
let currentToken: string | null = null;
let clearSession: () => void = () => {};
configureApi(
  async () => {
    if (supabase) return (await supabase.auth.getSession()).data.session?.access_token ?? null;
    return currentToken;
  },
  () => clearSession(),
);

function readDev(): string | null {
  try {
    return localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!supabase);
  const [token, setToken] = useState<string | null>(() => (supabase ? null : readDev()));
  currentToken = token;
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (supabase) {
      supabase.auth.getSession().then(({ data }) => {
        setToken(data.session?.access_token ?? null);
        setEmail(data.session?.user.email ?? null);
        setReady(true);
      });
      const { data } = supabase.auth.onAuthStateChange((_e, session) => {
        setToken(session?.access_token ?? null);
        setEmail(session?.user.email ?? null);
      });
      return () => data.subscription.unsubscribe();
    }
  }, []);

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(DEV_KEY);
    } catch {
      /* storage unavailable */
    }
    setToken(null);
    setEmail(null);
  }, []);

  clearSession = clear;

  const value = useMemo<AuthState>(
    () => ({
      ready,
      signedIn: !!token,
      email,
      async signInWithEmail(e, password) {
        if (!supabase) throw new Error("Email sign-in needs Supabase to be configured.");
        const { error } = await supabase.auth.signInWithPassword({ email: e, password });
        if (error) throw error;
      },
      async signUpWithEmail(e, password, name) {
        if (!supabase) throw new Error("Sign-up needs Supabase to be configured.");
        const { data, error } = await supabase.auth.signUp({ email: e, password, options: { data: { full_name: name } } });
        if (error) throw error;
        return data.session ? null : "Check your inbox to confirm your email, then sign in.";
      },
      async signInWithGoogle() {
        if (!supabase) throw new Error("Google sign-in needs Supabase to be configured.");
        const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin } });
        if (error) throw error;
      },
      async devSignIn(e, name) {
        const r = await fetch(api.base + "/api/dev/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: e, name }),
        });
        if (!r.ok) throw new Error("Development sign-in is not available on this server.");
        const { access_token } = await r.json();
        try {
          localStorage.setItem(DEV_KEY, access_token);
        } catch {
          /* storage unavailable: session lasts for this tab only */
        }
        currentToken = access_token;
        setToken(access_token);
        setEmail(e);
      },
      async signOut(everywhere = false) {
        if (everywhere) {
          try {
            await api.post("/api/me/sessions/revoke-all");
          } catch {
            /* still sign out locally */
          }
        }
        if (supabase) await supabase.auth.signOut({ scope: everywhere ? "global" : "local" });
        clear();
      },
    }),
    [ready, token, email, clear],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
