"use client";

import { ArrowLeft, Users } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { useDismiss } from "@/components/ui/useDismiss";
import { useWorkspace } from "@/state/workspace";

import styles from "./shell.module.css";

const SHORTCUTS = [
  ["/", "Поиск события"],
  ["Esc", "Закрыть панель"],
  ["Пробел", "Воспроизведение"],
];

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"root" | "team">("root");
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    setView("root");
  }, []);
  useDismiss(ref, open, close);
  const appMode = useWorkspace((state) => state.appMode);

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
      {open && view === "root" && (
        <div className={`${styles.menu} ${styles.userCard}`} data-align="right" role="dialog" aria-label="Профиль">
          <div className={styles.userName}>Дежурный оператор</div>
          <div className={styles.userRole}>
            Смена мониторинга · режим: {appMode === "live" ? "актуальные данные" : "сценарий"}
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
          <button type="button" className={styles.menuItem} style={{ marginTop: 4 }} onClick={() => setView("team")}>
            <Users size={14} strokeWidth={1.75} />
            О команде
          </button>
          <a href="/about" className={styles.menuItem} onClick={close}>
            О проекте
          </a>
        </div>
      )}
      {open && view === "team" && (
        <div className={`${styles.menu} ${styles.userCard}`} data-align="right" role="dialog" aria-label="О команде">
          <button type="button" className={styles.menuItem} style={{ marginBottom: 6 }} onClick={() => setView("root")}>
            <ArrowLeft size={14} strokeWidth={1.75} />
            Назад
          </button>
          <div className={styles.userName}>5BIT</div>
          <p className={styles.teamText}>
            5bit — команда разработчиков и ML-инженеров с опытом хакатонов, продуктовой разработки, backend, frontend, ML и geospatial задач.
          </p>
          <a href="/about" className={styles.menuItem} onClick={close}>
            Страница о проекте
          </a>
        </div>
      )}
    </div>
  );
}
