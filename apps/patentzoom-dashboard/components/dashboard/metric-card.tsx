import type { KpiCard } from "@patentzoom/seo-types";
import { ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function MetricCard({ item }: { item: KpiCard }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-muted-foreground">{item.label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between">
          <div className="text-3xl font-semibold tracking-tight">{item.value}</div>
          {item.delta ? (
            <div
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium",
                item.tone === "success" && "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
                item.tone === "warning" && "bg-amber-500/15 text-amber-600 dark:text-amber-300",
                item.tone === "danger" && "bg-rose-500/15 text-rose-600 dark:text-rose-300",
                item.tone === "default" && "bg-accent text-accent-foreground",
              )}
            >
              <ArrowUpRight className="h-3.5 w-3.5" />
              {item.delta}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

