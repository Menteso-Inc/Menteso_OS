import { AppShell } from "@/components/dashboard/app-shell";
import { PageFrame } from "@/components/dashboard/page-frame";

export default function AnalyticsPage() {
  return (
    <AppShell>
      <PageFrame
        title="Analytics"
        description="Track how AI-generated content performs across traffic, visibility, indexing, and article-level outcomes."
        chips={["traffic growth", "indexed pages", "content performance", "ranking placeholders"]}
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-border p-5">
            <p className="text-sm font-medium">Top performing blog</p>
            <p className="mt-2 text-lg font-semibold">How much does patent filing cost in the United States?</p>
            <p className="mt-2 text-sm text-muted-foreground">Leads impressions, clicks, and average position this month.</p>
          </div>
          <div className="rounded-2xl border border-border p-5">
            <p className="text-sm font-medium">Traffic growth</p>
            <p className="mt-2 text-3xl font-semibold">+8.4%</p>
            <p className="mt-2 text-sm text-muted-foreground">Search Console-backed trend available. External ranking provider still optional.</p>
          </div>
          <div className="rounded-2xl border border-dashed border-border p-5">
            <p className="text-sm font-medium">Ranking visibility</p>
            <p className="mt-2 text-lg font-semibold">Placeholder enabled</p>
            <p className="mt-2 text-sm text-muted-foreground">Reserved for future richer position tracking outside Search Console snapshots.</p>
          </div>
        </div>
      </PageFrame>
    </AppShell>
  );
}

