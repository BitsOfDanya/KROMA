import styles from "./shell.module.css";

export function Wordmark() {
  return (
    <span className={styles.brand}>
      <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M5 15.2A6.6 6.6 0 1 1 16.6 10" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        <path d="M12.9 13.6 L16.6 10" stroke="var(--incident-critical)" strokeWidth="1.7" strokeLinecap="round" />
      </svg>
      <span className={styles.wordmark}>KROMA</span>
    </span>
  );
}
