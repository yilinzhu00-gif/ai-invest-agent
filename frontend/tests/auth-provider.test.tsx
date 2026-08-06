import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "../components/auth-provider";

function AuthState() {
  const auth = useAuth();
  return <p>{auth.status}</p>;
}

describe("AuthProvider", () => {
  it("reports a configuration error instead of enabling unauthenticated production calls", async () => {
    render(
      <AuthProvider environment={{}}>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("configuration_error")).toBeInTheDocument();
  });
});
