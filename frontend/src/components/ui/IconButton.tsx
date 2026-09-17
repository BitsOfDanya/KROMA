import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import styles from "./ui.module.css";

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  label: string;
  icon: ReactNode;
  active?: boolean;
  shortcut?: string;
  tooltipSide?: "right" | "bottom" | "left" | "top";
  size?: "md" | "sm";
  showTooltip?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, active, shortcut, tooltipSide = "bottom", size = "md", showTooltip = true, className, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      data-active={active ? "true" : undefined}
      data-size={size}
      className={[styles.iconButton, className].filter(Boolean).join(" ")}
      {...props}
    >
      {icon}
      {showTooltip && (
        <span className={styles.tooltip} data-side={tooltipSide} aria-hidden="true">
          {label}
          {shortcut && <kbd>{shortcut}</kbd>}
        </span>
      )}
    </button>
  );
});
