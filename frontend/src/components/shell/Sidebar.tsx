"use client";

import { BarChart3, Flame, LayoutDashboard, RadioTower } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./shell.module.css";
import { Wordmark } from "./Wordmark";

const NAV = [
  { href: "/", label: "Обзор", icon: LayoutDashboard },
  { href: "/events", label: "События", icon: Flame },
  { href: "/analytics", label: "Аналитика", icon: BarChart3 },
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
            <Link key={item.href} href={item.href} className={styles.sideLink} aria-current={active ? "page" : undefined}>
              <Icon size={21} strokeWidth={1.8} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className={styles.sidebarFooter}>
        <span className={styles.sidebarPulse} aria-hidden="true" />
        <RadioTower size={16} strokeWidth={1.8} />
        <span>
          Оперативный контур
          <small>Спутниковый мониторинг</small>
        </span>
      </div>
    </aside>
  );
}
