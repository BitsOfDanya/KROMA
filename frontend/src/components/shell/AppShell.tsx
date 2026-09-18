import type { ReactNode } from "react";

import styles from "./shell.module.css";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <Sidebar />
      <TopBar />
      <main className={styles.main}>{children}</main>
    </div>
  );
}
