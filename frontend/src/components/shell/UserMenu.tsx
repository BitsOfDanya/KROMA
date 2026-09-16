"use client";

import { useCallback, useRef, useState } from "react";

import { useDismiss } from "@/components/ui/useDismiss";
import { useOverview } from "@/lib/api/queries";

import styles from "./shell.module.css";

const SHORTCUTS = [
  ["/", "Поиск события"],
  ["Esc", "Закрыть панель"],
  ["Пробел", "Воспроизведение"],
];

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const overview = useOverview();

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        className={styles.avatar}
        aria-label="Профиль оператора"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ДО
      </button>
      {open && (
        <div className={`${styles.menu} ${styles.userCard}`} data-align="right" role="dialog" aria-label="Профиль">
          <div className={styles.userName}>Дежурный оператор</div>
          <div className={styles.userRole}>
            Смена мониторинга · источник данных: {overview.data?.data_source === "demo" ? "демо-набор" : "—"}
          </div>
          <div className={styles.menuSection} style={{ paddingLeft: 0 }}>
            Клавиши
          </div>
          {SHORTCUTS.map(([key, label]) => (
            <div key={key} className={styles.shortcutRow}>
              {label}
              <kbd>{key}</kbd>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
