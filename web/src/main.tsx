import "./styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRootRoute, createRoute, createRouter, lazyRouteComponent, Outlet, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "@/components/layout/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import { SignIn } from "@/routes/SignIn";

const rootRoute = createRootRoute({ component: () => <Outlet /> });
const signIn = createRoute({ getParentRoute: () => rootRoute, path: "/signin", component: SignIn });
const app = createRoute({ getParentRoute: () => rootRoute, id: "app", component: AppShell });
const routes = [
  createRoute({ getParentRoute: () => app, path: "/", component: lazyRouteComponent(() => import("@/routes/Dashboard"), "Dashboard") }),
  createRoute({ getParentRoute: () => app, path: "/chat", component: lazyRouteComponent(() => import("@/routes/ChatPage"), "ChatPage") }),
  createRoute({ getParentRoute: () => app, path: "/chat/$chatId", component: lazyRouteComponent(() => import("@/routes/ChatPage"), "ChatPage") }),
  createRoute({ getParentRoute: () => app, path: "/holdings", component: lazyRouteComponent(() => import("@/routes/HoldingsPage"), "HoldingsPage") }),
  createRoute({ getParentRoute: () => app, path: "/holdings/$instrumentId", component: lazyRouteComponent(() => import("@/routes/InstrumentPage"), "InstrumentPage") }),
  createRoute({ getParentRoute: () => app, path: "/profile", component: lazyRouteComponent(() => import("@/routes/ProfilePage"), "ProfilePage") }),
  createRoute({ getParentRoute: () => app, path: "/settings", component: lazyRouteComponent(() => import("@/routes/SettingsPage"), "SettingsPage") }),
];
const router = createRouter({ routeTree: rootRoute.addChildren([signIn, app.addChildren(routes)]), defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider delayDuration={200}>
          <RouterProvider router={router} />
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
