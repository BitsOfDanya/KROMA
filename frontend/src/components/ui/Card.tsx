import type { HTMLAttributes, ReactNode } from "react";

import styles from "./ui.module.css";

interface CardProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
  padding?: "none" | "sm" | "md" | "lg";
  as?: "div" | "section" | "article";
}

export function Card({ children, padding = "none", as: Component = "section", className, ...props }: CardProps) {
  return (
    <Component className={[styles.card, className].filter(Boolean).join(" ")} data-padding={padding} {...props}>
      {children}
    </Component>
  );
}

export function CardHeader({ title, action, className }: { title: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <header className={[styles.cardHeader, className].filter(Boolean).join(" ")}>
      <h2 className={styles.cardTitle}>{title}</h2>
      {action && <div className={styles.cardAction}>{action}</div>}
    </header>
  );
}
