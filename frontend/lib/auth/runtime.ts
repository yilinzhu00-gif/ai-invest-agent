export type AuthMode = "oidc" | "development";
type PublicEnvironment = Record<string, string | undefined>;

export function readAuthMode(
  environment: PublicEnvironment,
): AuthMode {
  const configured = environment.NEXT_PUBLIC_AUTH_MODE?.trim();
  if (!configured) {
    throw new Error("Public auth mode configuration is incomplete");
  }
  if (configured !== "oidc" && configured !== "development") {
    throw new Error("Unsupported public auth mode");
  }
  return configured;
}

export function buildDevelopmentHeaders(
  principalId: string | undefined,
  workspaceId: string | undefined,
): Record<string, string> {
  const principal = principalId?.trim();
  const workspace = workspaceId?.trim();
  if (!principal || !workspace) {
    throw new Error("Development identity configuration is incomplete");
  }
  return {
    "X-Development-Principal-ID": principal,
    "X-Development-Workspace-ID": workspace,
  };
}
