"use client";

import { InMemoryWebStorage, UserManager, WebStorageStateStore } from "oidc-client-ts";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { buildAuthenticatedHeaders, readPublicOidcConfig, type PublicOidcConfig } from "../lib/auth/oidc";
import { buildDevelopmentHeaders, readAuthMode, type AuthMode } from "../lib/auth/runtime";

type PublicEnvironment = Record<string, string | undefined>;
type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "configuration_error";

export type AuthContextValue = {
  status: AuthStatus;
  mode: AuthMode | null;
  accessToken: string | null;
  workspaceId: string | null;
  requestHeaders: Record<string, string> | null;
  error: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
};

const defaultEnvironment: PublicEnvironment = {
  NEXT_PUBLIC_AUTH_MODE: process.env.NEXT_PUBLIC_AUTH_MODE,
  NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: process.env.NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID,
  NEXT_PUBLIC_OIDC_AUTHORITY: process.env.NEXT_PUBLIC_OIDC_AUTHORITY,
  NEXT_PUBLIC_OIDC_CLIENT_ID: process.env.NEXT_PUBLIC_OIDC_CLIENT_ID,
  NEXT_PUBLIC_OIDC_SCOPE: process.env.NEXT_PUBLIC_OIDC_SCOPE,
  NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: process.env.NEXT_PUBLIC_DEFAULT_WORKSPACE_ID,
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

function createManager(config: PublicOidcConfig): UserManager {
  return new UserManager({
    ...config,
    response_type: "code",
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
}

export function AuthProvider({
  children,
  environment = defaultEnvironment,
}: {
  children: ReactNode;
  environment?: PublicEnvironment;
}) {
  const managerRef = useRef<UserManager | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [requestHeaders, setRequestHeaders] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    try {
      const mode = readAuthMode(environment);
      setMode(mode);
      if (mode === "development") {
        const headers = buildDevelopmentHeaders(
          environment.NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID,
          environment.NEXT_PUBLIC_DEFAULT_WORKSPACE_ID,
        );
        setWorkspaceId(headers["X-Development-Workspace-ID"]);
        setRequestHeaders(headers);
        setStatus("authenticated");
        return () => { cancelled = true; };
      }
      const config = readPublicOidcConfig(environment);
      const configuredWorkspaceId = environment.NEXT_PUBLIC_DEFAULT_WORKSPACE_ID;
      if (!configuredWorkspaceId) throw new Error("OIDC workspace configuration is incomplete");
      const manager = createManager(config);
      managerRef.current = manager;
      const restoreUser = async () => {
        try {
          const user = window.location.pathname === "/oidc/callback"
            ? await manager.signinRedirectCallback()
            : await manager.getUser();
          if (cancelled) return;
          setWorkspaceId(configuredWorkspaceId);
          setAccessToken(user?.access_token ?? null);
          setRequestHeaders(user?.access_token
            ? buildAuthenticatedHeaders(user.access_token, configuredWorkspaceId)
            : null);
          setStatus(user?.access_token ? "authenticated" : "unauthenticated");
          if (window.location.pathname === "/oidc/callback") window.history.replaceState({}, "", "/agent-runs");
        } catch {
          if (!cancelled) {
            setError("无法完成身份登录，请重新登录。");
            setStatus("unauthenticated");
          }
        }
      };
      void restoreUser();
    } catch (caught) {
      if (!cancelled) {
        setError(caught instanceof Error ? caught.message : "OIDC configuration is invalid");
        setStatus("configuration_error");
      }
    }
    return () => { cancelled = true; };
  }, [environment]);

  const value: AuthContextValue = {
    status,
    mode,
    accessToken,
    workspaceId,
    requestHeaders,
    error,
    signIn: async () => { await managerRef.current?.signinRedirect(); },
    signOut: async () => { await managerRef.current?.signoutRedirect(); },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
