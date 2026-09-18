"use client";

import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { GlobalSearch } from "./GlobalSearch";
import { ModeSwitch } from "./ModeSwitch";
import { RegionSelect } from "./RegionSelect";
import styles from "./shell.module.css";
import { StatusIndicator } from "./StatusIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
const PAGE_TITLE: Record<string, string> = {
  "/": "Обзор",
  "/events": "События",
  "/analytics": "Аналитика",
};

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className={styles.topBar}>
      <div className={styles.pageIdentity}>
        <span className={styles.pageEyebrow}>Мониторинг пожаров</span>
        <div className={styles.pageTitle}>{PAGE_TITLE[pathname] ?? "KROMA"}</div>
      </div>
      <div className={styles.tools}>
        <Suspense>
          <GlobalSearch />
        </Suspense>
        <RegionSelect />
        <div className={styles.contextTools}>
          <ModeSwitch />
          <StatusIndicator />
        </div>
        <div className={styles.toolGroup}>
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
