"use client";

import { BarChart3, Flame, LayoutDashboard } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./shell.module.css";

const NAV = [
  { href: "/", label: "Обзор", icon: LayoutDashboard },
  { href: "/events", label: "События", icon: Flame },
  { href: "/analytics", label: "Аналитика", icon: BarChart3 },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className={styles.navigation} aria-label="Разделы">
      {NAV.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
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
