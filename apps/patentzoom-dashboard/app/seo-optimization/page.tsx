import { AppShell } from "@/components/dashboard/app-shell";
import { PageFrame } from "@/components/dashboard/page-frame";

export default function OptimizationPage() {
  return (
    <AppShell>
      <PageFrame
        title="SEO Optimization"
        description="Use AI to refresh outdated content, improve metadata, detect cannibalization, and strengthen internal linking."
        chips={["thin content detection", "metadata improvements", "cannibalization alerts", "refresh queue"]}
      >
        <div className="grid gap-4 lg:grid-cols-3">
          {[
            "12 articles have internal link opportunities ready for one-click refresh.",
            "3 pages are flagged as thin content and are queued for expansion.",
            "1 keyword cluster shows a cannibalization warning across two drafts.",
          ].map((item) => (
            <div key={item} className="rounded-2xl border border-border bg-accent/50 p-4 text-sm text-muted-foreground">{item}</div>
          ))}
        </div>
      </PageFrame>
    </AppShell>
  );
}

