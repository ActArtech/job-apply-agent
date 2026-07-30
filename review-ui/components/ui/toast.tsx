"use client";
import { useEffect, useState } from "react";

type Toast = { id: number; message: string; type: "success" | "error" | "info" };
let _setToast: ((t: Toast | null) => void) | null = null;

export function toast(message: string, type: Toast["type"] = "success") {
  _setToast?.({ id: Date.now(), message, type });
}

export function Toaster() {
  const [current, setCurrent] = useState<Toast | null>(null);

  useEffect(() => { _setToast = setCurrent; return () => { _setToast = null; }; }, []);
  useEffect(() => {
    if (!current) return;
    const t = setTimeout(() => setCurrent(null), 3000);
    return () => clearTimeout(t);
  }, [current]);

  if (!current) return null;
  const colors = {
    success: "bg-emerald-900 border-emerald-700 text-emerald-100",
    error: "bg-rose-900 border-rose-700 text-rose-100",
    info: "bg-[#1a1b18] border-border text-foreground",
  };
  return (
    <div className={`fixed top-4 right-4 z-50 max-w-sm rounded-md border px-4 py-3 text-sm font-mono shadow-lg ${colors[current.type]}`}>
      {current.message}
    </div>
  );
}
