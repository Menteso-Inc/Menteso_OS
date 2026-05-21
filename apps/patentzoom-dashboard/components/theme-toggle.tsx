"use client";

import { Moon, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  return (
    <Button variant="outline" size="sm" onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <SunMedium className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
      {dark ? "Light" : "Dark"}
    </Button>
  );
}

