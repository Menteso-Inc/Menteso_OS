import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead } from "@/components/ui/table";

export function DataTable({
  title,
  columns,
  rows,
}: {
  title: string;
  columns: string[];
  rows: Array<Array<string | number | React.ReactNode>>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <THead>
            <tr>
              {columns.map((column) => (
                <TH key={column}>{column}</TH>
              ))}
            </tr>
          </THead>
          <TBody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <TD key={`${rowIndex}-${cellIndex}`}>{cell}</TD>
                ))}
              </tr>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

