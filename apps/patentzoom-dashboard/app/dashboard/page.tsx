import { AppShell } from "@/components/dashboard/app-shell";
import { DataTable } from "@/components/dashboard/data-table";
import { MetricCard } from "@/components/dashboard/metric-card";
import { SectionHeader } from "@/components/dashboard/section-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getAutomationRules, getDashboardSummary, getPublishingLogs } from "@/lib/api";

export default async function DashboardPage() {
  const summary = await getDashboardSummary();
  const automations = await getAutomationRules();
  const logs = await getPublishingLogs();

  return (
    <AppShell>
      <SectionHeader
        title="Dashboard"
        description="A beginner-friendly command center for fully automated PatentZoom SEO operations."
        action="Create automation"
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {summary.kpis.map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>AI activity feed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {summary.activityFeed.map((item) => (
              <div key={item.id} className="rounded-2xl border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{item.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{item.message}</p>
                  </div>
                  <Badge variant={item.status === "warning" ? "warning" : "success"}>{item.status}</Badge>
                </div>
                <p className="mt-3 text-xs text-muted-foreground">{item.actor} · {new Date(item.createdAt).toLocaleString()}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>SEO visibility snapshot</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div>
              <div className="mb-2 flex items-center justify-between text-sm">
                <span>AI SEO score</span>
                <span className="font-medium">{summary.seoScore}/100</span>
              </div>
              <Progress value={summary.seoScore} />
            </div>
            <div className="rounded-2xl bg-accent p-4">
              <p className="text-sm font-medium">Attention needed</p>
              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                <li>1 publishing retry is waiting on category resolution.</li>
                <li>3 articles have indexing requests pending.</li>
                <li>Weekly SEO report automation is paused.</li>
              </ul>
            </div>
            <div className="space-y-3">
              {automations.slice(0, 3).map((rule) => (
                <div key={rule.id} className="flex items-center justify-between rounded-xl border border-border px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{rule.name}</p>
                    <p className="text-xs text-muted-foreground">{rule.schedule}</p>
                  </div>
                  <Badge variant={rule.state === "active" ? "success" : rule.state === "paused" ? "warning" : "danger"}>
                    {rule.state}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <DataTable
        title="Recent publishing logs"
        columns={["Article", "Destination", "Status", "Created", "Detail"]}
        rows={logs.map((log) => [
          log.articleTitle,
          log.destination,
          <Badge key={log.id} variant={log.status === "failed" ? "danger" : log.status === "processing" ? "warning" : "success"}>{log.status}</Badge>,
          new Date(log.createdAt).toLocaleString(),
          log.detail,
        ])}
      />
    </AppShell>
  );
}

