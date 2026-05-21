"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Sparkles } from "lucide-react";
import { PropsWithChildren, useState } from "react";
import { navigation } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

export function AppShell({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen surface-grid">
      <div className="flex min-h-screen">
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-40 w-72 border-r border-border bg-card/95 p-6 backdrop-blur md:static md:block",
            open ? "block" : "hidden md:block",
          )}
        >
          <div className="mb-8 flex items-center gap-3">
            <div className="rounded-2xl bg-primary/10 p-3 text-primary">
              <Sparkles className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">PatentZoom AI SEO</h1>
              <p className="text-sm text-muted-foreground">Autonomous content operations</p>
            </div>
          </div>
          <nav className="space-y-2">
            {navigation.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                  onClick={() => setOpen(false)}
                >
                  <item.icon className="h-4 w-4" />
                  {item.title}
                </Link>
              );
            })}
          </nav>
        </aside>
        <div className="flex flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 md:px-8">
              <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" className="md:hidden" onClick={() => setOpen((value) => !value)}>
                  <Menu className="h-4 w-4" />
                </Button>
                <div>
                  <p className="text-sm font-medium">PatentZoom SEO Command Center</p>
                  <p className="text-xs text-muted-foreground">Single workspace - WordPress + Search Console automation</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-300">
                  6 automations healthy
                </div>
                <ThemeToggle />
              </div>
            </div>
          </header>
          <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-4 py-8 md:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
