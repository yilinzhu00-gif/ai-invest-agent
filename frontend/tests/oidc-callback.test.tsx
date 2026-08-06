import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({ status: "authenticated" }),
}));

import OidcCallbackPage from "../app/oidc/callback/page";

describe("OIDC callback page", () => {
  it("navigates to research tasks after the provider completes login", async () => {
    render(<OidcCallbackPage />);

    expect(screen.getByText("正在完成安全登录，请稍候。")).toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/agent-runs"));
  });
});
