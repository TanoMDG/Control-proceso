export type PendingRecord = { id: string; module: string; payload: Record<string, unknown>; status: "pendiente" | "conflicto" | "error"; error?: string; route?: string; method?: "POST" | "PATCH" | "PUT" };
const DB = "control-procesos-offline";
const STORE = "registros";

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 2);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
function requestResult<T>(request: IDBRequest<T>, db: IDBDatabase): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => { db.close(); resolve(request.result); };
    request.onerror = () => { db.close(); reject(request.error); };
  });
}

export async function listPending(): Promise<PendingRecord[]> {
  const db = await database();
  return requestResult(db.transaction(STORE).objectStore(STORE).getAll(), db);
}

export async function savePending(record: PendingRecord): Promise<void> {
  const db = await database();
  await requestResult(db.transaction(STORE, "readwrite").objectStore(STORE).put(record), db);
}

export async function removePending(id: string): Promise<void> {
  const db = await database();
  await requestResult(db.transaction(STORE, "readwrite").objectStore(STORE).delete(id), db);
}

export function makePending(id: string, module: string, payload: Record<string, unknown>, error?: string): PendingRecord {
  return { id, module, payload, status: "pendiente", error };
}

export async function synchronize(token: string, apiUrl: string): Promise<void> {
  for (const row of await listPending()) {
    if (row.status !== "pendiente") continue;
    try {
      const response = await fetch(row.route ? `${apiUrl}${row.route}` : `${apiUrl}/registros/${row.module}`, { method: row.method ?? "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(row.payload) });
      if (response.ok) await removePending(row.id);
      else {
        const error = await response.text();
        await savePending({ ...row, status: response.status === 409 ? "conflicto" : response.status >= 400 && response.status < 500 ? "error" : "pendiente", error });
      }
    } catch {
      break;
    }
  }
}
