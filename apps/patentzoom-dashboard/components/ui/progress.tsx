export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-accent">
      <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

