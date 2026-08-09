export function buildAuthenticatedHeaders(accessToken: string, workspaceId: string): Record<string, string> {
  return {
    Authorization: `Bearer ${accessToken}`,
    "X-Workspace-ID": workspaceId,
  };
}

type PublicEnvironment = Record<string, string | undefined>;

export type PublicOidcConfig = {
  authority: string;
  client_id: string;
  redirect_uri: string;
  post_logout_redirect_uri: string;
  scope: string;
};

export function readPublicOidcConfig(
  environment: PublicEnvironment,
  origin = window.location.origin,
): PublicOidcConfig {
  const authority = environment.NEXT_PUBLIC_OIDC_AUTHORITY;
  const clientId = environment.NEXT_PUBLIC_OIDC_CLIENT_ID;
  if (!authority || !clientId) {
    throw new Error("OIDC public configuration is incomplete");
  }
  return {
    authority,
    client_id: clientId,
    redirect_uri: `${origin}/oidc/callback`,
    post_logout_redirect_uri: `${origin}/`,
    scope: environment.NEXT_PUBLIC_OIDC_SCOPE ?? "openid profile email agent:run",
  };
}
