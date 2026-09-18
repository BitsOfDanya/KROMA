"use client";

import Link from "next/link";
import { Suspense } from "react";

import { GlobalSearch } from "./GlobalSearch";
import { ModeSwitch } from "./ModeSwitch";
import { Navigation } from "./Navigation";
import { RegionSelect } from "./RegionSelect";
import styles from "./shell.module.css";
import { StatusIndicator } from "./StatusIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import { Wordmark } from "./Wordmark";

export function TopBar() {
  return (
    <header className={styles.topBar}>
      <Link href="/" aria-label="KROMA — обзор" className={styles.brandLink}>
        <Wordmark />
      </Link>
      <Navigation />
      <div className={styles.tools}>
        <Suspense>
          <GlobalSearch />
        </Suspense>
        <RegionSelect />
        <div className={styles.contextTools}>
          <Suspense>
            <ModeSwitch />
            <StatusIndicator />
          </Suspense>
        </div>
        <div className={styles.toolGroup}>
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
