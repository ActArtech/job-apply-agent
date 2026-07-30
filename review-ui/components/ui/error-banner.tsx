export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-rose-900/60 bg-rose-950/30 px-4 py-3">
      <span className="text-xs font-mono text-rose-300">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 rounded border border-rose-800 px-3 py-1 text-xs font-mono text-rose-300 hover:bg-rose-900/40 transition"
        >
          Retry
        </button>
      )}
    </div>
  );
}
