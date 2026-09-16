import type { CSSProperties } from "react";

import styles from "./ui.module.css";

export function Skeleton({ width = "100%", height = 12, style }: { width?: number | string; height?: number; style?: CSSProperties }) {
  return <span aria-hidden="true" className={styles.skeleton} style={{ width, height, ...style }} />;
}
