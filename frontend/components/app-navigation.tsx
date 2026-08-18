"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { href: "/", label: "研究总览" },
  { href: "/evidence", label: "证据库" },
  { href: "/agent-runs", label: "研究任务" },
  { href: "/scoring", label: "股票评分" },
] as const;

export function AppNavigation() {
  const pathname = usePathname();

  return (
    <header className="app-header">
      <div className="app-navigation">
        <Link className="app-brand" href="/">投研研究工作台</Link>
        <nav aria-label="主导航" className="app-navigation-links">
          {navigationItems.map((item) => {
            const current = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                aria-current={current ? "page" : undefined}
                className={current ? "app-navigation-link app-navigation-link--current" : "app-navigation-link"}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
