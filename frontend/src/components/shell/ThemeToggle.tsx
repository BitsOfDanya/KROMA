"use client";

import { Moon, Sun } from "lucide-react";

import { IconButton } from "@/components/ui/IconButton";
import { useTheme } from "@/state/theme";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "dark" ? "светлую" : "тёмную";
  return (
    <IconButton
      label={`Переключить на ${next} тему`}
      icon={theme === "dark" ? <Sun size={16} strokeWidth={1.75} /> : <Moon size={16} strokeWidth={1.75} />}
      onClick={toggleTheme}
      suppressHydrationWarning
    />
  );
}
