"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { GlobalSearch } from "./GlobalSearch";
import { LastUpdated } from "./LastUpdated";
import { RegionSelect } from "./RegionSelect";
import styles from "./shell.module.css";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import { Wordmark } from "./Wordmark";

const NAV = [
  { href: "/", label: "Обзор" },
  { href: "/events", label: "События" },
  { href: "/analytics", label: "Аналитика" },
];

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className={styles.topBar}>
      <Link href="/" aria-label="KROMA — обзор">
        <Wordmark />
      </Link>
      <nav className={styles.nav} aria-label="Разделы">
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className={styles.navLink} aria-current={pathname === item.href ? "page" : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className={styles.spacer} />
      <div className={styles.tools}>
        <Suspense>
          <GlobalSearch />
        </Suspense>
        <RegionSelect />
        <div className={styles.divider} />
        <LastUpdated />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
