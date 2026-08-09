import { describe, expect, it } from "vitest";

import { buildDevelopmentHeaders, readAuthMode } from "../lib/auth/runtime";

describe("auth runtime", () => {
  it("requires an explicit non-blank auth mode", () => {
    expect(() => readAuthMode({})).toThrow("Public auth mode configuration is incomplete");
    expect(() => readAuthMode({ NEXT_PUBLIC_AUTH_MODE: "   " }))
      .toThrow("Public auth mode configuration is incomplete");
  });

  it("rejects an unknown explicit auth mode", () => {
    expect(() => readAuthMode({ NEXT_PUBLIC_AUTH_MODE: "unsafe" }))
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
