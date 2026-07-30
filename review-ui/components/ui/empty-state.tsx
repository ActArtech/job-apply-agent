export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="text-4xl opacity-20">◉</div>
      <div className="font-mono text-sm font-semibold text-[#f5f6f4]">{title}</div>
      {description && <div className="max-w-xs text-xs text-muted">{description}</div>}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-2 rounded border border-border px-4 py-2 text-xs font-mono text-[#bfc2b9] hover:border-accent/60 hover:text-accent transition"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
