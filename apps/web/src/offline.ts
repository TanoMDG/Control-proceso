export type PendingRecord = { id: string; module: string; payload: Record<string, unknown>; status: "pendiente" | "conflicto" | "error"; error?: string };
const DB = "control-procesos-offline";
const STORE = "registros";

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
export async function listPending(): Promise<PendingRecord[]> { const db = await database(); return new Promise((resolve, reject) => { const request = db.transaction(STORE).objectStore(STORE).getAll(); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }); }
export async function savePending(record: PendingRecord) { const db = await database(); return new Promise<void>((resolve, reject) => { const request = db.transaction(STORE, "readwrite").objectStore(STORE).put(record); request.onsuccess = () => resolve(); request.onerror = () => reject(request.error); }); }
export async function removePending(id: string) { const db = await database(); return new Promise<void>((resolve, reject) => { const request = db.transaction(STORE, "readwrite").objectStore(STORE).delete(id); request.onsuccess = () => resolve(); request.onerror = () => reject(request.error); }); }
export function makePending(id: string, module: string, payload: Record<string, unknown>, online: boolean, error?: string): PendingRecord { return { id, module, payload, status: online ? "error" : "pendiente", error }; }
export async function synchronize(token: string, apiUrl: string) { for (const row of await listPending()) { try { const response = await fetch(`${apiUrl}/registros/${row.module}`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(row.payload) }); if (response.ok) await removePending(row.id); else await savePending({ ...row, status: response.status === 409 ? "conflicto" : "error", error: await response.text() }); } catch { break; } } }
