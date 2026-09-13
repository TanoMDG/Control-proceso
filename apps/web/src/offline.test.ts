import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listPending, makePending, removePending, savePending, synchronize } from "./offline";

function resetDatabase() {
  return new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase("control-procesos-offline");
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

describe("offline queue", () => {
  beforeEach(async () => { await resetDatabase(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("persists the original endpoint, method, and client UUID in IndexedDB", async () => {
    const record = { ...makePending("device-uuid", "m17", { client_uuid: "device-uuid" }), route: "/laboratorio/analisis", method: "POST" as const };
    await savePending(record);
    await expect(listPending()).resolves.toEqual([record]);
    await removePending(record.id);
    await expect(listPending()).resolves.toEqual([]);
  });

  it("synchronizes a pending revision to its original PUT endpoint", async () => {
    const record = { ...makePending("device-uuid", "m1", { client_uuid: "device-uuid", revision: 2 }), route: "/registros/m1/record-id", method: "PUT" as const };
    await savePending(record);
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await synchronize("token", "https://api.example/api/v1");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/api/v1/registros/m1/record-id", expect.objectContaining({ method: "PUT" }));
    await expect(listPending()).resolves.toEqual([]);
  });

  it("keeps conflicts for supervisor resolution and does not retry them", async () => {
    const record = makePending("device-uuid", "m1", { client_uuid: "device-uuid" });
    await savePending(record);
    const fetchMock = vi.fn().mockResolvedValue(new Response("conflict", { status: 409 }));
    vi.stubGlobal("fetch", fetchMock);
    await synchronize("token", "https://api.example/api/v1");
    await synchronize("token", "https://api.example/api/v1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(listPending()).resolves.toEqual([{ ...record, status: "conflicto", error: "conflict" }]);
  });

  it("marks client validation failures as errors instead of recoverable retries", async () => {
    const record = makePending("device-uuid", "m1", { client_uuid: "device-uuid" });
    await savePending(record);
    const fetchMock = vi.fn().mockResolvedValue(new Response("invalid", { status: 422 }));
    vi.stubGlobal("fetch", fetchMock);
    await synchronize("token", "https://api.example/api/v1");
    await synchronize("token", "https://api.example/api/v1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(listPending()).resolves.toEqual([{ ...record, status: "error", error: "invalid" }]);
  });
});
