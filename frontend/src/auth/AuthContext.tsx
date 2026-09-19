// Google Identity Services (GIS) sign-in, wired to the app's existing JWT
// storage in api/client.ts. This is the single source of truth for
// signed-in/signed-out state -- Sidebar (account UI) and SearchPage
// (gating "Start research") both read it via useAuth().

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  clearAuthToken,
  clearAuthUser,
  getAuthToken,
  getAuthUser,
  loginWithGoogle,
  setAuthToken,
  setAuthUser,
  type AuthUser,
} from "../api/client";

type AuthStatus = "signed-in" | "signed-out";

interface GoogleCredentialResponse {
  credential?: string;
}

interface GoogleAccountsId {
  initialize: (config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
  prompt: () => void;
  disableAutoSelect: () => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "").trim();
const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  /** True once window.google.accounts.id is initialized and ready to render a button / prompt. */
  scriptReady: boolean;
  signInError: string | null;
  /** Opens Google's One Tap / account chooser directly (e.g. from a gated action). */
  promptSignIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join(""),
    );
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function stringClaim(payload: Record<string, unknown> | null, key: string): string | null {
  const value = payload?.[key];
  return typeof value === "string" ? value : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(getAuthToken() ? "signed-in" : "signed-out");
  const [user, setUser] = useState<AuthUser | null>(getAuthUser());
  const [scriptReady, setScriptReady] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);

  const handleCredential = useCallback(async (response: GoogleCredentialResponse) => {
    if (!response.credential) return;
    setSignInError(null);
    try {
      const { access_token } = await loginWithGoogle(response.credential);
      const googlePayload = decodeJwtPayload(response.credential);
      const nextUser: AuthUser = {
        name: stringClaim(googlePayload, "name"),
        email: stringClaim(googlePayload, "email"),
        picture: stringClaim(googlePayload, "picture"),
      };
      setAuthToken(access_token);
      setAuthUser(nextUser);
      setUser(nextUser);
      setStatus("signed-in");
    } catch {
      setSignInError("Google sign-in failed. Please try again.");
    }
  }, []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;

    function initialize() {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          void handleCredential(response);
        },
      });
      setScriptReady(true);
    }

    if (window.google?.accounts?.id) {
      initialize();
      return;
    }

    const script = document.querySelector<HTMLScriptElement>(`script[src="${GIS_SCRIPT_SRC}"]`);
    if (!script) return;
    script.addEventListener("load", initialize);
    return () => script.removeEventListener("load", initialize);
  }, [handleCredential]);

  const signOut = useCallback(() => {
    clearAuthToken();
    clearAuthUser();
    setStatus("signed-out");
    setUser(null);
    window.google?.accounts.id.disableAutoSelect();
  }, []);

  const promptSignIn = useCallback(() => {
    setSignInError(null);
    window.google?.accounts.id.prompt();
  }, []);

  const value = useMemo(
    () => ({ status, user, scriptReady, signInError, promptSignIn, signOut }),
    [status, user, scriptReady, signInError, promptSignIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
