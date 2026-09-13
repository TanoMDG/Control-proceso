import { afterEach, describe, expect, it, vi } from "vitest";
import { registerServiceWorker } from "./pwa";

describe("PWA service worker", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it("registers the offline shell worker at the application root", () => {
    const register = vi.fn();
    vi.stubGlobal("navigator", { serviceWorker: { register } });
    registerServiceWorker();
    expect(register).toHaveBeenCalledWith("/sw.js");
  });
});
