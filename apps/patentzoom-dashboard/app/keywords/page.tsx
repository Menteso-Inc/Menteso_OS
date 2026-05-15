import { AppShell } from "@/components/dashboard/app-shell";
import { DataTable } from "@/components/dashboard/data-table";
import { PageFrame } from "@/components/dashboard/page-frame";
import { Badge } from "@/components/ui/badge";
import { getKeywords } from "@/lib/api";

export default async function KeywordsPage() {
  const keywords = await getKeywords();
  return (
    <AppShell>
      <PageFrame
        title="Keywords"
        description="Discover low competition, high intent opportunities and push them into AI writing queues."
        chips={["SERPAPI discovery", "intent scoring", "topic clustering", "competitor ideas"]}
      >
        <DataTable
          title="Keyword discovery queue"
          columns={["Keyword", "Cluster", "Intent", "Volume", "Difficulty", "CPC", "Competition", "Status"]}
          rows={keywords.map((keyword) => [
            keyword.keyword,
            keyword.cluster,
            keyword.intent,
            keyword.volume,
            keyword.difficulty,
            `$${keyword.cpc.toFixed(2)}`,
            <Badge key={keyword.id} variant={keyword.competitionTier === "low" ? "success" : keyword.competitionTier === "medium" ? "warning" : "danger"}>{keyword.competitionTier}</Badge>,
            keyword.status,
          ])}
        />
      </PageFrame>
    </AppShell>
  );
}

