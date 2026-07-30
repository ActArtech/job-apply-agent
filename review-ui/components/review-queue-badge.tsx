"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";

export function ReviewQueueBadge() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    api.analytics.funnel()
      .then((f) => setCount(Math.max(0, f.generated - f.reviewed)))
      .catch(() => {});
  }, []);

  if (!count) return null;

  return (
    <span className="ml-1.5 rounded-full bg-accent px-1.5 py-px font-mono text-[9px] font-bold leading-none text-accent-foreground">
      {count}
    </span>
  );
}
