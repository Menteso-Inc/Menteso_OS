import { AppShell } from "@/components/dashboard/app-shell";
import { DataTable } from "@/components/dashboard/data-table";
import { PageFrame } from "@/components/dashboard/page-frame";
import { Badge } from "@/components/ui/badge";
import { getArticles } from "@/lib/api";

export default async function ArticlesPage() {
  const articles = await getArticles();
  return (
    <AppShell>
      <PageFrame
        title="Articles"
        description="Manage the full article lifecycle from draft generation through publishing and indexing."
        chips={["preview", "edit", "regenerate", "publish now", "schedule"]}
      >
        <DataTable
          title="Article pipeline"
          columns={["Title", "Primary keyword", "Status", "SEO score", "Readability", "Updated", "Mode"]}
          rows={articles.map((article) => [
            article.title,
            article.primaryKeyword,
            <Badge key={article.id} variant={article.status === "Published" || article.status === "Indexed" ? "success" : article.status === "Reviewing" ? "warning" : "default"}>{article.status}</Badge>,
            article.seoScore,
            article.readabilityScore,
            new Date(article.updatedAt).toLocaleString(),
            article.authoringMode,
          ])}
        />
      </PageFrame>
    </AppShell>
  );
}

