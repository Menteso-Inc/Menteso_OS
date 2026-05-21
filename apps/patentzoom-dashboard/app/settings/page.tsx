import { AppShell } from "@/components/dashboard/app-shell";
import { PageFrame } from "@/components/dashboard/page-frame";

export default function SettingsPage() {
  return (
    <AppShell>
      <PageFrame
        title="Settings"
        description="Configure APIs, WordPress publishing defaults, Google integrations, and automation rules for the single PatentZoom workspace."
        chips={["OpenAI", "SERPAPI", "WordPress", "Google Search Console", "Indexing API", "publishing defaults"]}
      >
        <div className="grid gap-4 md:grid-cols-2">
          {[
            "OpenAI API key and model selection",
            "SERPAPI API key and discovery defaults",
            "WordPress credentials, categories, and publishing behavior",
            "Google Search Console and Indexing API credentials",
          ].map((item) => (
            <div key={item} className="rounded-2xl border border-border p-4 text-sm text-muted-foreground">{item}</div>
          ))}
        </div>
      </PageFrame>
    </AppShell>
  );
}
