import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

import styles from "./ui.module.css";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  inputClassName?: string;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { icon, inputClassName, className, ...props },
  ref,
) {
  return (
    <span className={[styles.fieldShell, className].filter(Boolean).join(" ")} data-icon={icon ? "true" : undefined}>
      {icon && <span className={styles.fieldIcon}>{icon}</span>}
      <input ref={ref} className={[styles.fieldControl, inputClassName].filter(Boolean).join(" ")} {...props} />
    </span>
  );
});

export function SelectField({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={[styles.selectControl, className].filter(Boolean).join(" ")} {...props}>
      {children}
    </select>
  );
}
