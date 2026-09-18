import type { ReactNode } from "react";

import styles from "./ui.module.css";

export function PageHeader({
  title,
  description,
  meta,
  actions,
  className,
}: {
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={[styles.pageHeader, className].filter(Boolean).join(" ")}>
      <div className={styles.pageHeading}>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {meta && <div className={styles.pageMeta}>{meta}</div>}
      {actions && <div className={styles.pageActions}>{actions}</div>}
    </header>
  );
}
