"use client";

import { Moon, Sun } from "lucide-react";
import { useLang } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

export function ThemeToggle({ className = "theme-button" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLang();
  const label = theme === "dark" ? t("lightMode") : t("darkMode");

  return (
    <button
      type="button"
      className={className}
      onClick={toggleTheme}
      aria-label={label}
      title={label}
    >
      {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  );
}
