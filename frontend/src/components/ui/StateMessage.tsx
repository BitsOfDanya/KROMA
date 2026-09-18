import { AlertTriangle, Inbox, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";

import styles from "./ui.module.css";

interface StateMessageProps {
  title: string;
  detail?: ReactNode;
  tone?: "empty" | "error";
  align?: "start" | "center";
  action?: ReactNode;
}

export function StateMessage({ title, detail, tone = "empty", align = "start", action }: StateMessageProps) {
  return (
    <div className={styles.stateMessage} data-tone={tone} data-align={align} role={tone === "error" ? "alert" : "status"}>
      <div className={styles.stateTitle}>
        {tone === "error" ? <AlertTriangle size={15} strokeWidth={1.75} /> : <Inbox size={15} strokeWidth={1.75} />}
        {title}
      </div>
      {detail && <div className={styles.stateDetail}>{detail}</div>}
      {action}
    </div>
  );
}

export function ErrorMessage({
  error,
  onRetry,
  retrying,
  align,
}: {
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  align?: "start" | "center";
}) {
  const network = error instanceof ApiError && error.isNetworkError;
  const title = network ? "Не удаётся связаться с сервером" : "Не удалось загрузить данные";
  const detail = network
    ? "Проверьте подключение к интернету и попробуйте ещё раз."
    : "Попробуйте обновить данные чуть позже. Если ошибка повторится, обратитесь к администратору.";
  return (
    <StateMessage
      tone="error"
      title={title}
      detail={detail}
      align={align}
      action={
        onRetry && (
          <button type="button" className={styles.textButton} onClick={onRetry} disabled={retrying}>
            <RotateCw size={13} strokeWidth={1.75} />
            {retrying ? "Загружаем…" : "Попробовать снова"}
          </button>
        )
      }
    />
  );
}
