import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
type Mua = { id: string; codigo: string; fecha_generacion: string; composicion: Array<{ componente: string; referencia?: string }> };
type Trace = { aristas: Array<{ relacion: string; origen: string; destino: string; desde: string; hasta: string | null; certeza: string }> };

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada.");
  const [pending, setPending] = useState<PendingRecord[]>([]);
  const [muas, setMuas] = useState<Mua[]>([]);
  const [preparador, setPreparador] = useState("");
  const [componente, setComponente] = useState("");
  const [referencia, setReferencia] = useState("");
  const [muaId, setMuaId] = useState("");
  const [box, setBox] = useState("");
  const [trace, setTrace] = useState<Trace | null>(null);

  useEffect(() => {
    if (!token) return;
    const refresh = () => { void listPending().then(setPending); };
    const online = async () => { await synchronize(token, apiUrl); refresh(); };
    refresh();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [token]);

  useEffect(() => {
    if (token) void loadMuas();
  }, [token]);

  async function request(route: string, payload?: Record<string, unknown>, method: "GET" | "POST" = "GET") {
    const response = await fetch(`${apiUrl}${route}`, { method, headers: { Authorization: `Bearer ${token}`, ...(payload ? { "Content-Type": "application/json" } : {}) }, body: payload ? JSON.stringify(payload) : undefined });
    if (!response.ok) {
      const error = Object.assign(new Error(await response.text()), { status: response.status });
      throw error;
    }
    return response.json();
  }

  async function loadMuas() {
    try {
      const rows = await request("/mua") as Mua[];
      setMuas(rows);
      if (!muaId && rows[0]) setMuaId(rows[0].id);
    } catch (error) { setMessage(`No fue posible cargar MUA: ${String(error)}`); }
  }

  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request("/auth/login", { username, password }, "POST") as { access_token: string };
      sessionStorage.setItem("access_token", result.access_token);
      setToken(result.access_token);
      setMessage("Sesion iniciada.");
      void loadMuas();
    } catch { setMessage("No fue posible iniciar sesion. Verifique sus credenciales."); }
  }

  async function createMua(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request("/mua", { id_preparador: preparador, composicion: [{ componente, ...(referencia ? { referencia } : {}) }] }, "POST") as Mua;
      setMuas((previous) => [...previous, result]); setMuaId(result.id); setComponente(""); setReferencia("");
      setMessage(`${result.codigo} registrada.`);
    } catch (error) { setMessage(`M4 no se guardo: ${String(error)}`); }
  }

  async function loadMuaInBox(event: FormEvent) {
    event.preventDefault();
    const payload = { id_mua: muaId, box, desde: new Date().toISOString(), certeza: "CONFIRMADA" };
    try {
      await request("/trazabilidad/mua-box", payload, "POST");
      setBox(""); setMessage("M5 sincronizado: presencia MUA-box registrada.");
    } catch (error) {
      const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
      if (status && status < 500) { setMessage(`M5 no se guardo: ${String(error)}`); return; }
      const queued = { ...makePending(crypto.randomUUID(), "m5", payload, navigator.onLine, String(error)), route: "/trazabilidad/mua-box", method: "POST" as const };
      await savePending(queued); setPending(await listPending());
      setMessage("M5 quedo en cola local para sincronizar.");
    }
  }

  async function loadTrace() {
    if (!muaId) return;
    try { setTrace(await request(`/mua/${muaId}/trazabilidad`) as Trace); }
    catch (error) { setMessage(`No fue posible consultar trazabilidad: ${String(error)}`); }
  }

  return <main><section className="panel"><p className="eyebrow">F4 · MUA y trazabilidad</p><h1>Control de Proceso</h1><p className="subtitle">Preparacion de Pasta</p>{!token ? <form onSubmit={login}><label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label><button>Iniciar sesion</button></form> : <section className="forms"><div className="form-actions"><button type="button" onClick={loadMuas}>Actualizar MUA</button><button type="button" onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button></div><section className="traceability"><h2>M4 · Identidad y composicion MUA</h2><form onSubmit={createMua}><label>UUID del preparador<input value={preparador} onChange={(event) => setPreparador(event.target.value)} placeholder="UUID de la persona palero" required /></label><label>Componente<input value={componente} onChange={(event) => setComponente(event.target.value)} required /></label><label>Referencia/lote<input value={referencia} onChange={(event) => setReferencia(event.target.value)} /></label><button>Registrar MUA</button></form></section><section className="traceability"><h2>M5 · Carga y presencia en box</h2><form onSubmit={loadMuaInBox}><label>MUA<select value={muaId} onChange={(event) => setMuaId(event.target.value)} required><option value="">Seleccione una MUA</option>{muas.map((mua) => <option key={mua.id} value={mua.id}>{mua.codigo} · {mua.fecha_generacion}</option>)}</select></label><label>Box<input value={box} onChange={(event) => setBox(event.target.value)} required /></label><button>Registrar presencia</button></form></section><section className="traceability"><h2>Trazabilidad temporal</h2><button type="button" onClick={loadTrace}>Ver secuencia de la MUA</button>{trace?.aristas.map((edge, index) => <p key={`${edge.relacion}-${index}`}><strong>{edge.certeza}</strong> · {edge.origen} → {edge.destino} · {new Date(edge.desde).toLocaleString()}{edge.hasta ? ` a ${new Date(edge.hasta).toLocaleString()}` : " (vigente)"}</p>)}<p className="inline-note">La secuencia muestra CONFIRMADA, POTENCIAL o INFERIDA y nunca calcula porcentajes o toneladas no registrados.</p></section><section className="offline"><h2>Sincronizacion offline</h2>{pending.map((row) => <p key={row.id}>{row.module.toUpperCase()}: {row.status} {row.error}</p>)}</section></section>}<p className="message">{message}</p></section></main>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
