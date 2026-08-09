import { describe, expect, it } from "vitest";

import { buildDevelopmentHeaders, readAuthMode } from "../lib/auth/runtime";

describe("auth runtime", () => {
  it("defaults next dev to development and production builds to oidc", () => {
    expect(readAuthMode({}, "development")).toBe("development");
    expect(readAuthMode({}, "production")).toBe("oidc");
  });

  it("rejects an unknown explicit auth mode", () => {
    expect(() => readAuthMode({ NEXT_PUBLIC_AUTH_MODE: "unsafe" }, "development"))
      .toThrow("Unsupported public auth mode");
  });

  it("builds only explicit development identity headers", () => {
    expect(buildDevelopmentHeaders("local-user", "local-workspace")).toEqual({
      "X-Development-Principal-ID": "local-user",
      "X-Development-Workspace-ID": "local-workspace",
    });
    expect(() => buildDevelopmentHeaders("   ", "local-workspace"))
      .toThrow("Development identity configuration is incomplete");
  });
});
