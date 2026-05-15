import { AppShell } from "@/components/dashboard/app-shell";
import { DataTable } from "@/components/dashboard/data-table";
import { PageFrame } from "@/components/dashboard/page-frame";
import { Badge } from "@/components/ui/badge";
import { getPublishingLogs } from "@/lib/api";

export default async function PublishingPage() {
  const logs = await getPublishingLogs();
  return (
    <AppShell>
      <PageFrame
        title="Publishing"
        description="Monitor WordPress health, category and tag resolution, featured images, retries, and queue throughput."
        chips={["WordPress REST API", "featured image upload", "publishing queue", "retry logs"]}
      >
        <DataTable
          title="Publishing queue logs"
          columns={["Article", "Destination", "Status", "Created", "Detail"]}
          rows={logs.map((log) => [
            log.articleTitle,
            log.destination,
            <Badge key={log.id} variant={log.status === "failed" ? "danger" : log.status === "processing" ? "warning" : "success"}>{log.status}</Badge>,
            new Date(log.createdAt).toLocaleString(),
            log.detail,
          ])}
        />
      </PageFrame>
    </AppShell>
  );
}

