export function registerServiceWorker(): void {
  if ("serviceWorker" in navigator) void navigator.serviceWorker.register("/sw.js");
}
