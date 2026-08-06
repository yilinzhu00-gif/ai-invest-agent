import { describe, expect, it } from "vitest";

import { buildAuthenticatedHeaders, readPublicOidcConfig } from "../lib/auth/oidc";

describe("OIDC request boundary", () => {
  it("sends a bearer token and workspace without development identity headers", () => {
    const headers = buildAuthenticatedHeaders("access-token", "workspace-a");

    expect(headers).toMatchObject({
      Authorization: "Bearer access-token",
      "X-Workspace-ID": "workspace-a",
    });
    expect(headers).not.toHaveProperty("X-Development-Principal-ID");
    expect(headers).not.toHaveProperty("X-Development-Workspace-ID");
  });
});

describe("public OIDC configuration", () => {
  it("requires a public authority and client id", () => {
    expect(() => readPublicOidcConfig({})).toThrow("OIDC public configuration is incomplete");
  });

  it("builds callback URLs from the browser origin", () => {
    expect(
      readPublicOidcConfig(
        {
          NEXT_PUBLIC_OIDC_AUTHORITY: "https://login.example.com/oidc",
          NEXT_PUBLIC_OIDC_CLIENT_ID: "public-client",
          NEXT_PUBLIC_OIDC_SCOPE: "openid profile agent:run",
        },
        "https://aiinvestmentagent.cn",
      ),
    ).toMatchObject({
      authority: "https://login.example.com/oidc",
      client_id: "public-client",
      redirect_uri: "https://aiinvestmentagent.cn/oidc/callback",
      post_logout_redirect_uri: "https://aiinvestmentagent.cn/",
      scope: "openid profile agent:run",
    });
  });
});
