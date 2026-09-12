import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const RESPONSIBLES_PENDING = "Pendiente de configuracion: no hay responsables de mantenimiento configurados.";
type Mua = { id: string; codigo: string; fecha_generacion: string };
type Trace = { aristas: Array<{ relacion: string; origen: string; destino: string; desde: string; hasta: string | null; certeza: string }> };
type Equipment = { id: string; codigo: string; descripcion: string; sector: string };
type Responsible = { id: string; legajo: string; apellido_nombre: string };
type ResponsibleResponse = { responsables: Responsible[]; mensaje_configuracion: string | null };

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada.");
  const [pending, setPending] = useState<PendingRecord[]>([]);
  const [muas, setMuas] = useState<Mua[]>([]);
  const [preparador, setPreparador] = useState("");
  const [componente, setComponente] = useState("");
  const [muaId, setMuaId] = useState("");
  const [box, setBox] = useState("");
  const [trace, setTrace] = useState<Trace | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [responsibles, setResponsibles] = useState<Responsible[]>([]);
  const [responsibleMessage, setResponsibleMessage] = useState<string | null>(null);
  const [equipmentId, setEquipmentId] = useState("");
  const [responsibleId, setResponsibleId] = useState("");
  const [maintenanceType, setMaintenanceType] = useState("CORRECTIVO");
  const [maintenanceDescription, setMaintenanceDescription] = useState("");
  const [madirexNote, setMadirexNote] = useState("");

  useEffect(() => {
    if (!token) return;
    const refresh = () => { void listPending().then(setPending); };
    const online = async () => { await synchronize(token, apiUrl); refresh(); };
    refresh();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    void loadMuas();
    void loadMaintenanceConfiguration();
  }, [token]);

  async function request(route: string, payload?: Record<string, unknown>, method: "GET" | "POST" = "GET") {
    const response = await fetch(`${apiUrl}${route}`, { method, headers: { Authorization: `Bearer ${token}`, ...(payload ? { "Content-Type": "application/json" } : {}) }, body: payload ? JSON.stringify(payload) : undefined });
    if (!response.ok) throw Object.assign(new Error(await response.text()), { status: response.status });
    return response.json();
  }

  async function loadMuas() {
    try {
      const rows = await request("/mua") as Mua[];
      setMuas(rows);
      if (!muaId && rows[0]) setMuaId(rows[0].id);
    } catch (error) { setMessage(`No fue posible cargar MUA: ${String(error)}`); }
  }

  async function loadMaintenanceConfiguration() {
    try {
      const [configuredEquipment, configuredResponsibles] = await Promise.all([
        request("/mantenimiento/equipos") as Promise<Equipment[]>,
        request("/mantenimiento/responsables") as Promise<ResponsibleResponse>,
      ]);
      setEquipment(configuredEquipment);
      setResponsibles(configuredResponsibles.responsables);
      setResponsibleMessage(configuredResponsibles.mensaje_configuracion);
      if (!equipmentId && configuredEquipment[0]) setEquipmentId(configuredEquipment[0].id);
      if (!responsibleId && configuredResponsibles.responsables[0]) setResponsibleId(configuredResponsibles.responsables[0].id);
    } catch (error) { setMessage(`No fue posible cargar la configuracion M7: ${String(error)}`); }
  }

  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request("/auth/login", { username, password }, "POST") as { access_token: string };
      sessionStorage.setItem("access_token", result.access_token);
      setToken(result.access_token);
      setMessage("Sesion iniciada.");
    } catch { setMessage("No fue posible iniciar sesion. Verifique sus credenciales."); }
  }

  async function createMua(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request("/mua", { id_preparador: preparador, composicion: [{ componente }] }, "POST") as Mua;
      setMuas((previous) => [...previous, result]);
      setMuaId(result.id);
      setComponente("");
      setMessage(`${result.codigo} registrada.`);
    } catch (error) { setMessage(`M4 no se guardo: ${String(error)}`); }
  }

  async function loadMuaInBox(event: FormEvent) {
    event.preventDefault();
    const payload = { id_mua: muaId, box, desde: new Date().toISOString(), certeza: "CONFIRMADA" };
    try {
      await request("/trazabilidad/mua-box", payload, "POST");
      setBox("");
      setMessage("M5 sincronizado: presencia MUA-box registrada.");
    } catch (error) {
      const code = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
      if (code && code < 500) { setMessage(`M5 no se guardo: ${String(error)}`); return; }
      await savePending({ ...makePending(crypto.randomUUID(), "m5", payload, navigator.onLine, String(error)), route: "/trazabilidad/mua-box", method: "POST" });
      setPending(await listPending());
      setMessage("M5 quedo en cola local para sincronizar.");
    }
  }

  async function createMaintenance(event: FormEvent) {
    event.preventDefault();
    if (!responsibleId) { setMessage(responsibleMessage ?? RESPONSIBLES_PENDING); return; }
    const clientUuid = crypto.randomUUID();
    const now = new Date();
    const payload = { client_uuid: clientUuid, fecha_operativa: now.toISOString().slice(0, 10), turno_codigo: "ACTUAL", inicio: now.toISOString(), id_equipo: equipmentId, id_responsable: responsibleId, tipo: maintenanceType, descripcion: maintenanceDescription, campos_madirex: madirexNote ? { observacion: madirexNote } : {} };
    try {
      await request("/mantenimiento/registros", payload, "POST");
      setMaintenanceDescription("");
      setMadirexNote("");
      setMessage("M7 registrado. Los campos Madirex son informativos.");
    } catch (error) {
      const code = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
      if (code && code < 500) { setMessage(`M7 no se guardo: ${String(error)}`); return; }
      await savePending({ ...makePending(clientUuid, "m7", payload, navigator.onLine, String(error)), route: "/mantenimiento/registros", method: "POST" });
      setPending(await listPending());
      setMessage("M7 quedo en cola local para sincronizar.");
    }
  }

  async function loadTrace() {
    if (!muaId) return;
    try { setTrace(await request(`/mua/${muaId}/trazabilidad`) as Trace); }
    catch (error) { setMessage(`No fue posible consultar trazabilidad: ${String(error)}`); }
  }

  return <main><section className="panel"><p className="eyebrow">F5 · Mantenimiento, MUA y trazabilidad</p><h1>Control de Proceso</h1><p className="subtitle">Preparacion de Pasta</p>{!token ? <form onSubmit={login}><label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label><button>Iniciar sesion</button></form> : <section className="forms"><div className="form-actions"><button type="button" onClick={loadMuas}>Actualizar MUA</button><button type="button" onClick={loadMaintenanceConfiguration}>Actualizar configuracion M7</button><button type="button" onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button></div><section className="traceability"><h2>M7 · Registro de mantenimiento</h2>{responsibleMessage && <p className="warning">{responsibleMessage}</p>}<form onSubmit={createMaintenance}><label>Equipo<select value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)} required disabled={!equipment.length}><option value="">Seleccione un equipo</option>{equipment.map((item) => <option key={item.id} value={item.id}>{item.codigo} · {item.descripcion}</option>)}</select></label><label>Responsable de mantenimiento<select value={responsibleId} onChange={(event) => setResponsibleId(event.target.value)} required disabled={!responsibles.length}><option value="">Seleccione un responsable</option>{responsibles.map((item) => <option key={item.id} value={item.id}>{item.legajo} · {item.apellido_nombre}</option>)}</select></label><label>Tipo<select value={maintenanceType} onChange={(event) => setMaintenanceType(event.target.value)}><option>CORRECTIVO</option><option>PREVENTIVO</option><option>INSPECCION</option></select></label><label>Trabajo realizado<textarea value={maintenanceDescription} onChange={(event) => setMaintenanceDescription(event.target.value)} required /></label><label>Madirex (informativo)<input value={madirexNote} onChange={(event) => setMadirexNote(event.target.value)} placeholder="No genera limite ni desvio" /></label><button disabled={!equipment.length || !responsibles.length}>Registrar M7</button></form></section><section className="traceability"><h2>M4 · Identidad y composicion MUA</h2><form onSubmit={createMua}><label>UUID del preparador<input value={preparador} onChange={(event) => setPreparador(event.target.value)} required /></label><label>Componente<input value={componente} onChange={(event) => setComponente(event.target.value)} required /></label><button>Registrar MUA</button></form></section><section className="traceability"><h2>M5 · Carga y presencia en box</h2><form onSubmit={loadMuaInBox}><label>MUA<select value={muaId} onChange={(event) => setMuaId(event.target.value)} required><option value="">Seleccione una MUA</option>{muas.map((mua) => <option key={mua.id} value={mua.id}>{mua.codigo} · {mua.fecha_generacion}</option>)}</select></label><label>Box<input value={box} onChange={(event) => setBox(event.target.value)} required /></label><button>Registrar presencia</button></form></section><section className="traceability"><h2>Trazabilidad temporal</h2><button type="button" onClick={loadTrace}>Ver secuencia de la MUA</button>{trace && <ul>{trace.aristas.map((edge, index) => <li key={`${edge.relacion}-${index}`}>{edge.relacion}: {edge.origen} a {edge.destino} ({edge.certeza})</li>)}</ul>}</section><section className="pending"><h2>Cola offline</h2>{pending.length ? <ul>{pending.map((item) => <li key={item.id}>{item.module.toUpperCase()} · {item.status}{item.error ? `: ${item.error}` : ""}</li>)}</ul> : <p>Sin registros pendientes.</p>}</section></section>}<p className="status">{message}</p></section></main>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
