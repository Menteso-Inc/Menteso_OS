import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SectionHeader } from "@/components/dashboard/section-header";

export function PageFrame({
  title,
  description,
  chips,
  children,
}: {
  title: string;
  description: string;
  chips?: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-6">
      <SectionHeader title={title} description={description} />
      {chips?.length ? (
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <Badge key={chip}>{chip}</Badge>
          ))}
        </div>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>{title} overview</CardTitle>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  );
}

