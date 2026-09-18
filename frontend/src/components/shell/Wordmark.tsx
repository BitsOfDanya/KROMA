import styles from "./shell.module.css";

export function Wordmark() {
  return (
    <span className={styles.brand}>
      <svg className={styles.logoMark} width="42" height="42" viewBox="0 0 42 42" aria-hidden="true">
        <path className={styles.logoTile} d="M11 2h20a9 9 0 0 1 9 9v20a9 9 0 0 1-9 9H11a9 9 0 0 1-9-9V11a9 9 0 0 1 9-9Z" />
        <path className={styles.logoFlame} d="M22.1 8.2c1.2 5.4-3.2 6.9-2.2 10.4.6 2 2.1 2.5 2.5 4.6.4 1.8-.4 3.2-1.7 4.1 4.5-.1 7.3-2.9 7.3-7 0-4.5-3.2-7.1-5.9-12.1Z" />
        <path className={styles.logoFlameAlt} d="M18.6 16.2c-3 2.4-5 5-5 8.1 0 4.1 3.1 7.1 7.5 7.1 3.5 0 6.2-1.9 6.8-5-1.3 1.8-3.1 2.7-5.2 2.7-3.6 0-6.1-2.4-6.1-5.8 0-2.2 1-4.4 2-7.1Z" />
        <circle className={styles.logoSignal} cx="21" cy="23.5" r="2.2" />
      </svg>
      <span className={styles.wordmark}>KROMA<span>Geo Intelligence</span></span>
    </span>
  );
}
