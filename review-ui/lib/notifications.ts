export function notifyRunDone(phase: string, status: string): void {
  if (typeof window === "undefined") return;
  if (!("Notification" in window)) return;
  if (!document.hidden && document.hasFocus()) return;
  if (Notification.permission === "default") {
    Notification.requestPermission();
    return;
  }
  if (Notification.permission !== "granted") return;
  new Notification(`${phase} ${status}`, {
    body:
      status === "succeeded"
        ? "Pipeline run completed successfully."
        : "Pipeline run failed — check logs.",
  });
}

export function requestNotificationPermission(): void {
  if (typeof window === "undefined") return;
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}
