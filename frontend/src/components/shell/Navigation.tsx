"use client";

import { BarChart3, Database, Flame, LayoutDashboard, MapPinned } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import styles from "./shell.module.css";

const NAV = [
  { href: "/", label: "Обзор", icon: LayoutDashboard, match: "exact" as const },
  { href: "/events", label: "События", icon: Flame, match: "exact" as const },
  { href: "/analytics", label: "Аналитика", icon: BarChart3, match: "analytics" as const },
  { href: "/analytics?tab=area", label: "Анализ", icon: MapPinned, match: "area" as const },
  { href: "/explorer", label: "Данные", icon: Database, match: "exact" as const },
];

function NavigationLinks() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const areaTab = searchParams.get("tab") === "area";

  return (
    <nav className={styles.navigation} aria-label="Разделы">
      {NAV.map((item) => {
        const Icon = item.icon;
        const active =
          item.match === "area"
            ? pathname === "/analytics" && areaTab
            : item.match === "analytics"
              ? pathname === "/analytics" && !areaTab
              : pathname === item.href;
        return (
          <Link key={item.href} href={item.href} className={styles.navLink} aria-label={item.label} aria-current={active ? "page" : undefined}>
            <Icon size={18} strokeWidth={1.8} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function Navigation() {
  return (
    <Suspense fallback={<nav className={styles.navigation} aria-label="Разделы" />}>
      <NavigationLinks />
    </Suspense>
  );
}
