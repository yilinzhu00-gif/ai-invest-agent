import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "../components/auth-provider";

function AuthState() {
  const auth = useAuth();
  return <>
    <p>{`${auth.status}|${auth.mode}`}</p>
    <p>{JSON.stringify(auth.requestHeaders)}</p>
  </>;
}

describe("AuthProvider", () => {
  it("reports a configuration error instead of enabling unauthenticated production calls", async () => {
    render(
      <AuthProvider environment={{ NEXT_PUBLIC_AUTH_MODE: "oidc" }}>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("configuration_error|oidc")).toBeInTheDocument();
  });

  it("authenticates an explicitly configured development identity", async () => {
    render(
      <AuthProvider environment={{
        NEXT_PUBLIC_AUTH_MODE: "development",
        NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: "local-user",
        NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: "local-workspace",
      }}>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("authenticated|development")).toBeInTheDocument();
    expect(screen.getByText(/X-Development-Principal-ID/)).toHaveTextContent("local-user");
  });

  it("reports a configuration error for an unknown auth mode", async () => {
    render(
      <AuthProvider environment={{ NEXT_PUBLIC_AUTH_MODE: "unsafe" }}>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("configuration_error|null")).toBeInTheDocument();
  });

  it.each([
    ["NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID", { NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: "   " }],
    ["NEXT_PUBLIC_DEFAULT_WORKSPACE_ID", { NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: "   " }],
  ])("reports a configuration error for blank development %s", async (_name, blankValue) => {
    render(
      <AuthProvider environment={{
        NEXT_PUBLIC_AUTH_MODE: "development",
        NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: "local-user",
        NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: "local-workspace",
        ...blankValue,
      }}>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("configuration_error|development")).toBeInTheDocument();
  });
});
