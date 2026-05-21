import { AppShell } from "@/components/dashboard/app-shell";
import { PageFrame } from "@/components/dashboard/page-frame";

export default function SearchConsolePage() {
  return (
    <AppShell>
      <PageFrame
        title="Search Console"
        description="Track indexing requests, coverage health, and article-level search performance. Some ranking analytics remain explicitly partial in phase 1."
        chips={["indexing requests", "impressions", "clicks", "CTR", "average position", "partial analytics"]}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-border p-4">
            <p className="text-sm font-medium">Indexed vs pending</p>
            <p className="mt-2 text-sm text-muted-foreground">31 indexed · 3 pending · 1 API warning</p>
          </div>
          <div className="rounded-2xl border border-dashed border-border p-4">
            <p className="text-sm font-medium">Phase 1 analytics note</p>
            <p className="mt-2 text-sm text-muted-foreground">External rank tracking is shown as a placeholder until broader SEO telemetry is connected.</p>
          </div>
        </div>
      </PageFrame>
    </AppShell>
  );
}

