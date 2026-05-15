import { AppShell } from "@/components/dashboard/app-shell";
import { PageFrame } from "@/components/dashboard/page-frame";

export default function WriterPage() {
  return (
    <AppShell>
      <PageFrame
        title="AI Writer"
        description="Turn approved keywords into structured article briefs, SEO drafts, schema, FAQ sections, and internal link plans."
        chips={["OpenAI briefs", "SEO scoring", "readability", "schema + FAQ", "plagiarism placeholder"]}
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[
            "Generate title, meta title, and meta description automatically.",
            "Build H1/H2/H3 structures with semantic NLP coverage.",
            "Create FAQ schema, alt text, slugs, and internal link suggestions.",
          ].map((item) => (
            <div key={item} className="rounded-2xl border border-border bg-accent/50 p-4 text-sm text-muted-foreground">{item}</div>
          ))}
        </div>
      </PageFrame>
    </AppShell>
  );
}

