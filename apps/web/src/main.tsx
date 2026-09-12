import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [dashboard, setDashboard] = useState<{ ultimo_recalculo: string | null; hechos: Array<{ fecha_operativa: string; turno: string; contexto: string; metricas: Record<string, unknown> }> } | null>(null);
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada por ADMIN.");
  const [module, setModule] = useState("M1");
  const [turno, setTurno] = useState("08-16");
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<Record<string, string>>({ box_activo: "1", humedad_verdes: "", residuo: "", aeroseparador: "" });
  const [pending, setPending] = useState<PendingRecord[]>([]);

  useEffect(() => { if (!token) return; const refresh = () => listPending().then(setPending); const online = async () => { await synchronize(token, apiUrl); refresh(); }; refresh(); window.addEventListener("online", online); return () => window.removeEventListener("online", online); }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    const response = await fetch(`${apiUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      setMessage("No fue posible iniciar sesion. Verifique sus credenciales.");
      return;
    }
    const token = await response.json() as { access_token: string };
    sessionStorage.setItem("access_token", token.access_token);
    setToken(token.access_token);
    setMessage("Sesion iniciada. Puede imprimir formularios de transicion FT.");
  }

  async function printForm(module: string) {
    const response = await fetch(`${apiUrl}/exportar?modulo=${module}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) {
      setMessage("No fue posible obtener el formulario.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
  }

  async function loadDashboard() {
    const response = await fetch(`${apiUrl}/kpi`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("No fue posible cargar el dashboard."); return; }
    setDashboard(await response.json());
  }

  function changeModule(value: string) { setModule(value); setData(value === "M1" ? { box_activo: "1", humedad_verdes: "", residuo: "", aeroseparador: "" } : value === "M2" ? { caudal_pasta: "", caudal_agua: "", humedad_salida: "" } : value === "M3" ? { tipo_registro: "lecho", humedad: "", temperatura: "" } : { causa: "P01", inicio: "", fin: "", descripcion: "" }); }
  function setField(key: string, value: string) { setData((previous) => ({ ...previous, [key]: value })); }
  async function submitRecord(event: FormEvent) {
    event.preventDefault();
    const instant = module === "M6" && data.inicio ? new Date(data.inicio).toISOString() : new Date().toISOString();
    const payload = { client_uuid: crypto.randomUUID(), fecha_operativa: fecha, turno_codigo: turno, instante_medicion: instant, origen_dato: "digital_directo", datos: data };
    try {
      const response = await fetch(`${apiUrl}/registros/${module.toLowerCase()}`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await response.text());
      setMessage(`${module} sincronizado.`);
    } catch (error) {
      const row: PendingRecord = makePending(payload.client_uuid, module.toLowerCase(), payload, navigator.onLine, error instanceof Error ? error.message : "Error de sincronizacion");
      await savePending(row); setPending(await listPending()); setMessage(`${module} guardado localmente para sincronizar.`);
    }
  }

  return <main>
    <section className="panel">
      <p className="eyebrow">F0 · Fundamentos</p>
      <h1>Control de Proceso</h1>
      <p className="subtitle">Preparacion de Pasta</p>
      {!token ? <form onSubmit={login}>
        <label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
        <label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label>
        <button type="submit">Iniciar sesion</button>
      </form> : <section className="forms">
        <h2>Formularios de transicion</h2>
        <p>Imprima y complete fecha, hora, turno y responsable. La carga posterior conserva esos datos originales.</p>
        {["m1", "m2", "m3", "m6", "m10"].map((module) => <button key={module} onClick={() => printForm(module)}>Imprimir {module.toUpperCase()}</button>)}
        <button onClick={loadDashboard}>Actualizar dashboard</button>
        {dashboard && <section className="dashboard"><h2>Dashboard M14</h2><p>Ultimo recálculo: {dashboard.ultimo_recalculo ?? "Sin recálculo"}</p>{dashboard.hechos.map((fact) => <article key={`${fact.fecha_operativa}-${fact.turno}-${fact.contexto}`}><strong>{fact.fecha_operativa} · {fact.turno} · {fact.contexto}</strong><pre>{JSON.stringify(fact.metricas, null, 2)}</pre></article>)}</section>}
        <form className="operational" onSubmit={submitRecord}><h2>Registro operativo F1</h2><label>Modulo<select value={module} onChange={(event) => changeModule(event.target.value)}><option>M1</option><option>M2</option><option>M3</option><option>M6</option></select></label><label>Fecha operativa<input type="date" value={fecha} onChange={(event) => setFecha(event.target.value)} required /></label><label>Turno<input value={turno} onChange={(event) => setTurno(event.target.value)} required /></label>{module === "M1" && <><label>Box<select value={data.box_activo} onChange={(event) => setField("box_activo", event.target.value)}><option>1</option><option>2</option><option>3</option><option>6</option></select></label><label>Humedad Verdes<input required type="number" step="any" value={data.humedad_verdes} onChange={(event) => setField("humedad_verdes", event.target.value)} /></label><label>Residuo<input required type="number" step="any" value={data.residuo} onChange={(event) => setField("residuo", event.target.value)} /></label><label>Aeroseparador<input required type="number" step="any" value={data.aeroseparador} onChange={(event) => setField("aeroseparador", event.target.value)} /></label></>}{module === "M2" && <><label>Caudal pasta<input required type="number" step="any" value={data.caudal_pasta} onChange={(event) => setField("caudal_pasta", event.target.value)} /></label><label>Caudal agua<input required type="number" step="any" value={data.caudal_agua} onChange={(event) => setField("caudal_agua", event.target.value)} /></label><label>Humedad salida<input required type="number" step="any" value={data.humedad_salida} onChange={(event) => setField("humedad_salida", event.target.value)} /></label></>}{module === "M3" && <><label>Tipo<select value={data.tipo_registro} onChange={(event) => setData({ tipo_registro: event.target.value })}><option value="lecho">Lecho fluido</option><option value="ksider_rechazo">K-Sider</option><option value="stock_silo">Stock silo</option></select></label>{data.tipo_registro === "lecho" && <><label>Humedad<input required type="number" step="any" value={data.humedad ?? ""} onChange={(event) => setField("humedad", event.target.value)} /></label><label>Temperatura<input required type="number" step="any" value={data.temperatura ?? ""} onChange={(event) => setField("temperatura", event.target.value)} /></label></>}{data.tipo_registro === "ksider_rechazo" && <><label>Humedad K-Sider<input required type="number" step="any" value={data.humedad_ksider ?? ""} onChange={(event) => setField("humedad_ksider", event.target.value)} /></label><label>Segundos de pesada<input required value={data.segundos_pesada ?? "60"} onChange={(event) => setField("segundos_pesada", event.target.value)} /></label></>}{data.tipo_registro === "stock_silo" && <><label>Silo<input required type="number" min="1" max="16" value={data.silo ?? ""} onChange={(event) => setField("silo", event.target.value)} /></label><label>Linea<select value={data.linea ?? "L7"} onChange={(event) => setField("linea", event.target.value)}><option>L6</option><option>L7</option></select></label><label>Altura libre (m)<input required type="number" min="0" max="11" step="any" value={data.altura_libre_m ?? ""} onChange={(event) => setField("altura_libre_m", event.target.value)} /></label></>}</>}{module === "M6" && <><label>Causa<select value={data.causa} onChange={(event) => setField("causa", event.target.value)}>{Array.from({ length: 12 }, (_, index) => <option key={index}>P{String(index + 1).padStart(2, "0")}</option>)}</select></label><label>Inicio<input required type="datetime-local" value={data.inicio} onChange={(event) => setField("inicio", event.target.value)} /></label><label>Fin<input type="datetime-local" value={data.fin} onChange={(event) => setField("fin", event.target.value)} /></label>{data.causa === "P12" && <label>Descripcion<input required value={data.descripcion} onChange={(event) => setField("descripcion", event.target.value)} /></label>}</>}<button type="submit">Guardar {module}</button></form>
        <section><h2>Sincronizacion offline</h2><button onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button>{pending.map((row) => <p key={row.id}>{row.module.toUpperCase()}: {row.status} {row.error}</p>)}</section>
      </section>}
      <p className="message" role="status">{message}</p>
    </section>
  </main>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
