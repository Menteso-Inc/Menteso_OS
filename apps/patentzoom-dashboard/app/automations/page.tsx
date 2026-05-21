import { AppShell } from "@/components/dashboard/app-shell";
import { DataTable } from "@/components/dashboard/data-table";
import { PageFrame } from "@/components/dashboard/page-frame";
import { Badge } from "@/components/ui/badge";
import { getAutomationRules } from "@/lib/api";

export default async function AutomationsPage() {
  const automations = await getAutomationRules();
  return (
    <AppShell>
      <PageFrame
        title="Automations"
        description="Create and monitor the repeating AI workflows that power PatentZoom SEO operations."
        chips={["daily keyword research", "auto article generation", "auto publish", "weekly reports"]}
      >
        <DataTable
          title="Automation rules"
          columns={["Name", "Schedule", "State", "Last run", "Next run", "Description"]}
          rows={automations.map((rule) => [
            rule.name,
            rule.schedule,
            <Badge key={rule.id} variant={rule.state === "active" ? "success" : rule.state === "paused" ? "warning" : "danger"}>{rule.state}</Badge>,
            rule.lastRunAt ? new Date(rule.lastRunAt).toLocaleString() : "—",
            rule.nextRunAt ? new Date(rule.nextRunAt).toLocaleString() : "—",
            rule.description,
          ])}
        />
      </PageFrame>
    </AppShell>
  );
}

