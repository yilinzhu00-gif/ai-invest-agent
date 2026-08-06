import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({
    status: "authenticated",
    accessToken: "access-token",
    workspaceId: "workspace-a",
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));

import { AgentRunPanel } from "../components/agent-run-panel";

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("agent run authentication", () => {
  it("uses the OIDC access token and workspace instead of development headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      id: "00000000-0000-0000-0000-000000000005",
      status: "queued",
      executor_mode: "celery",
    }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.type(screen.getByLabelText("研究问题"), "上证指数走势");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      headers: expect.objectContaining({
        Authorization: "Bearer access-token",
        "X-Workspace-ID": "workspace-a",
      }),
    });
    expect(fetchMock.mock.calls[0]?.[1]?.headers).not.toHaveProperty("X-Development-Principal-ID");
  });
});
