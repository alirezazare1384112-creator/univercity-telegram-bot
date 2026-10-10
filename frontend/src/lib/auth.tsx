import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api } from "./api";
import { initTelegram } from "./telegram";
import type { Me } from "./types";

type AuthState =
  | { status: "loading" }
  | { status: "guest" }
  | { status: "error"; message: string }
  | { status: "ready"; user: Me };

interface AuthContextValue {
  state: AuthState;
  /** Re-fetch /api/me from scratch (full loading state). */
  retry: () => void;
  /** Patch the current user without re-fetching (e.g. after profile edit). */
  updateUser: (user: Me) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Fire-and-forget diagnostics beacon (survives page close, no auth). */
function reportBoot(payload: Record<string, unknown>): void {
  try {
    navigator.sendBeacon(
      "/api/boot-report",
      new Blob([JSON.stringify(payload)], { type: "application/json" }),
    );
  } catch {
    // diagnostics must never break the app
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const attemptRef = useRef(0);
  const probeTimeoutRef = useRef<number | null>(null);

  const retry = useCallback(() => {
    const attempt = ++attemptRef.current;
    setState({ status: "loading" });

    const probe = (round: number) => {
      if (attemptRef.current !== attempt) return;
      const webApp = initTelegram();
      if (round === 0) {
        reportBoot({
          event: "probe",
          telegram: Boolean(webApp),
          initDataLen: webApp?.initData?.length ?? 0,
          platform: webApp?.platform ?? null,
          version: webApp?.version ?? null,
          hashLen: window.location.hash.length,
          ua: navigator.userAgent,
        });
      }
      if (webApp?.initData) {
        api
          .me()
          .then((user) => {
            if (attemptRef.current !== attempt) return;
            setState({ status: "ready", user });
            webApp.HapticFeedback?.notificationOccurred("success");
          })
          .catch((error: unknown) => {
            if (attemptRef.current !== attempt) return;
            const message =
              error instanceof ApiError
                ? `احراز هویت ناموفق: ${error.message}`
                : "ارتباط با سرور برقرار نشد";
            reportBoot({
              event: "me-failed",
              status: error instanceof ApiError ? error.status : 0,
              message,
            });
            setState({ status: "error", message });
            webApp.HapticFeedback?.notificationOccurred("error");
          });
        return;
      }
      // Some Android clients deliver initData a moment after page load;
      // probe for ~8s before concluding the app was opened without auth data.
      if (round < 26) {
        probeTimeoutRef.current = window.setTimeout(() => probe(round + 1), 300);
        return;
      }
      reportBoot({ event: "guest", initDataLen: 0 });
      setState({ status: "guest" });
    };

    probe(0);
  }, []);

  /** Patch the user in place without a full re-fetch. Used by the profile
   *  page after a successful edit so the screen doesn't flash a spinner. */
  const updateUser = useCallback((user: Me) => {
    setState({ status: "ready", user });
  }, []);

  useEffect(() => {
    retry();
    // Cleanup: clear any pending probe timeout when the provider unmounts
    // so we don't try to setState on an unmounted component.
    return () => {
      if (probeTimeoutRef.current !== null) {
        window.clearTimeout(probeTimeoutRef.current);
      }
    };
  }, [retry]);

  return (
    <AuthContext.Provider value={{ state, retry, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
