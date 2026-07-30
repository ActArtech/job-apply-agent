export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-[#232421] ${className}`} />;
}

export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
