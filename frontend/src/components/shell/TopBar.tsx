"use client";

import Link from "next/link";
import { Suspense } from "react";

import { ModeSwitch } from "./ModeSwitch";
import { Navigation } from "./Navigation";
import { RegionSelect } from "./RegionSelect";
import styles from "./shell.module.css";
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
        <RegionSelect />
        <div className={styles.contextTools}>
          <Suspense>
            <ModeSwitch />
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
