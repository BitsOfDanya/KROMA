"use client";

import { BarChart3, Flame, LayoutDashboard } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./shell.module.css";
import { Wordmark } from "./Wordmark";

const NAV = [
  { href: "/", label: "Обзор", description: "Вся картина на карте", icon: LayoutDashboard },
  { href: "/events", label: "События", description: "Что требует внимания", icon: Flame },
  { href: "/analytics", label: "Аналитика", description: "Динамика и последствия", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className={styles.sidebar}>
      <Link href="/" aria-label="KROMA — обзор" className={styles.brandLink}>
        <Wordmark />
      </Link>
      <nav className={styles.sideNav} aria-label="Разделы">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className={styles.sideLink} aria-label={item.label} aria-current={active ? "page" : undefined}>
              <Icon size={21} strokeWidth={1.8} />
              <span>{item.label}<small className={styles.sideDescription}>{item.description}</small></span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
