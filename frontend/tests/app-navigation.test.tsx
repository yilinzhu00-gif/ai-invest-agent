import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const currentPath = vi.hoisted(() => ({ value: "/agent-runs" }));

vi.mock("next/navigation", () => ({
  usePathname: () => currentPath.value,
}));

import { AppNavigation } from "../components/app-navigation";

describe("app navigation", () => {
  it("keeps the research overview reachable from every main workspace page", () => {
    render(<AppNavigation />);

    expect(screen.getByRole("link", { name: "研究总览" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "研究任务" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "证据库" })).toHaveAttribute("href", "/evidence");
    expect(screen.getByRole("link", { name: "股票评分" })).toHaveAttribute("href", "/scoring");
  });
});
