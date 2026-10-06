import {
  createContext,
  useCallback,
  useContext,
  useEffect,
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
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const retry = useCallback(() => {
    setState({ status: "loading" });
    const webApp = initTelegram();
    if (!webApp?.initData) {
      setState({ status: "guest" });
      return;
    }
    api
      .me()
      .then((user) => {
        setState({ status: "ready", user });
        webApp.HapticFeedback?.notificationOccurred("success");
      })
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError
            ? `احراز هویت ناموفق: ${error.message}`
            : "ارتباط با سرور برقرار نشد";
        setState({ status: "error", message });
        webApp.HapticFeedback?.notificationOccurred("error");
      });
  }, []);

  useEffect(() => {
    retry();
  }, [retry]);

  return <AuthContext.Provider value={{ state, retry }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
