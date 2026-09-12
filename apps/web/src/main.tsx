import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const pressesByLine: Record<string, string[]> = { L6: ["PH Siti"], L7: ["PH5000-1", "PH5000-2"] };
const formats = ["64x64", "64x122"];
type Dashboard = { ultimo_recalculo: string | null; hechos: Array<{ fecha_operativa: string; turno: string; contexto: string; metricas: Record<string, unknown> }> };

function initialData(module: string): Record<string, string> {
  if (module === "M1") return { box_activo: "1", humedad_verdes: "", residuo: "", aeroseparador: "" };
  if (module === "M2") return { caudal_pasta: "", caudal_agua: "", humedad_salida: "" };
  if (module === "M3") return { tipo_registro: "lecho", humedad: "", temperatura: "" };
  if (module === "M6") return { causa: "P01", inicio: "", fin: "", descripcion: "" };
  if (module === "M8") return { linea: "L7", prensa: "PH5000-1", causa_vaciado: "", duracion_min: "10" };
  if (module === "M9") return { linea: "L7", prensa: "PH5000-1", formato: "64x64", humedad_pasta: "", presion: "", humedad_residual: "" };
  return { linea: "L7", formato: "64x64" };
}

function inputId(press: string, cavity: number, sector: number) {
  return `espesor:${press}:${cavity}:${sector}`;
}

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada por ADMIN.");
  const [module, setModule] = useState("M1");
  const [turno, setTurno] = useState("08-16");
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<Record<string, string>>(initialData("M1"));
  const [pending, setPending] = useState<PendingRecord[]>([]);

  useEffect(() => {
    if (!token) return;
    const refresh = () => { void listPending().then(setPending); };
    const online = async () => { await synchronize(token, apiUrl); refresh(); };
    refresh();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    const response = await fetch(`${apiUrl}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
    if (!response.ok) { setMessage("No fue posible iniciar sesion. Verifique sus credenciales."); return; }
    const result = await response.json() as { access_token: string };
    sessionStorage.setItem("access_token", result.access_token);
    setToken(result.access_token);
    setMessage("Sesion iniciada.");
  }

  async function printForm(formModule: string) {
    const response = await fetch(`${apiUrl}/exportar?modulo=${formModule}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("No fue posible obtener el formulario."); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
  }

  async function loadDashboard() {
    const response = await fetch(`${apiUrl}/kpi`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("No fue posible cargar el dashboard."); return; }
    setDashboard(await response.json() as Dashboard);
  }

  function changeModule(value: string) { setModule(value); setData(initialData(value)); }
  function setField(key: string, value: string) { setData((previous) => ({ ...previous, [key]: value })); }
  function changeLine(line: string) {
    setData((previous) => ({ ...previous, linea: line, prensa: pressesByLine[line][0] }));
  }

  function recordData(): Record<string, unknown> {
    if (module !== "M10") return data;
    const details = pressesByLine[data.linea].flatMap((press) => [1, 2].flatMap((cavity) => Array.from({ length: 9 }, (_, index) => ({
      prensa: press,
      cavidad: cavity,
      sector: index + 1,
      espesor_mm: data[inputId(press, cavity, index + 1)] ?? "",
    }))));
    return { linea: data.linea, formato: data.formato, detalles: details };
  }

  async function submitRecord(event: FormEvent) {
    event.preventDefault();
    const instant = module === "M6" && data.inicio ? new Date(data.inicio).toISOString() : new Date().toISOString();
    const payload = { client_uuid: crypto.randomUUID(), fecha_operativa: fecha, turno_codigo: turno, instante_medicion: instant, origen_dato: "digital_directo", datos: recordData() };
    try {
      const response = await fetch(`${apiUrl}/registros/${module.toLowerCase()}`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
      if (response.ok) { setMessage(`${module} sincronizado.`); return; }
      const error = await response.text();
      if (response.status < 500) { setMessage(`${module} no se guardo: ${error}`); return; }
      const row = makePending(payload.client_uuid, module.toLowerCase(), payload, true, error);
      await savePending(row);
      setPending(await listPending());
      setMessage(`${module} quedo en cola por un error temporal del servidor.`);
    } catch (error) {
      const row = makePending(payload.client_uuid, module.toLowerCase(), payload, navigator.onLine, error instanceof Error ? error.message : "Error de sincronizacion");
      await savePending(row);
      setPending(await listPending());
      setMessage(`${module} guardado localmente para sincronizar.`);
    }
  }

  function commonFields() {
    return <><label>Fecha operativa<input type="date" value={fecha} onChange={(event) => setFecha(event.target.value)} required /></label><label>Turno<input value={turno} onChange={(event) => setTurno(event.target.value)} required /></label></>;
  }

  function lineAndPress(withFormat = false) {
    return <><label>Linea<select value={data.linea} onChange={(event) => changeLine(event.target.value)}><option value="L6">L6</option><option value="L7">L7</option></select></label><label>Prensa<select value={data.prensa} onChange={(event) => setField("prensa", event.target.value)}>{pressesByLine[data.linea].map((press) => <option key={press}>{press}</option>)}</select></label>{withFormat && <label>Formato<select value={data.formato} onChange={(event) => setField("formato", event.target.value)}>{formats.map((format) => <option key={format}>{format}</option>)}</select></label>}</>;
  }

  function moduleFields() {
    if (module === "M1") return <><label>Box<select value={data.box_activo} onChange={(event) => setField("box_activo", event.target.value)}><option>1</option><option>2</option><option>3</option><option>6</option></select></label><NumberField label="Humedad Verdes" value={data.humedad_verdes} onChange={(value) => setField("humedad_verdes", value)} /><NumberField label="Residuo" value={data.residuo} onChange={(value) => setField("residuo", value)} /><NumberField label="Aeroseparador" value={data.aeroseparador} onChange={(value) => setField("aeroseparador", value)} /></>;
    if (module === "M2") return <><NumberField label="Caudal pasta" value={data.caudal_pasta} onChange={(value) => setField("caudal_pasta", value)} /><NumberField label="Caudal agua" value={data.caudal_agua} onChange={(value) => setField("caudal_agua", value)} /><NumberField label="Humedad salida" value={data.humedad_salida} onChange={(value) => setField("humedad_salida", value)} /></>;
    if (module === "M3") return <><label>Tipo<select value={data.tipo_registro} onChange={(event) => setData({ tipo_registro: event.target.value })}><option value="lecho">Lecho fluido</option><option value="ksider_rechazo">K-Sider</option><option value="stock_silo">Stock silo</option></select></label>{data.tipo_registro === "lecho" && <><NumberField label="Humedad" value={data.humedad} onChange={(value) => setField("humedad", value)} /><NumberField label="Temperatura" value={data.temperatura} onChange={(value) => setField("temperatura", value)} /></>}{data.tipo_registro === "ksider_rechazo" && <><NumberField label="Humedad K-Sider" value={data.humedad_ksider} onChange={(value) => setField("humedad_ksider", value)} /><NumberField label="Segundos pesada" value={data.segundos_pesada} onChange={(value) => setField("segundos_pesada", value)} /></>}{data.tipo_registro === "stock_silo" && <><label>Silo<input required type="number" min="1" max="16" value={data.silo} onChange={(event) => setField("silo", event.target.value)} /></label><label>Linea<select value={data.linea} onChange={(event) => setField("linea", event.target.value)}><option>L7</option><option>L6</option></select></label><NumberField label="Altura libre (m)" value={data.altura_libre_m} onChange={(value) => setField("altura_libre_m", value)} /></>}</>;
    if (module === "M6") return <><label>Causa<input required value={data.causa} onChange={(event) => setField("causa", event.target.value)} /></label><label>Inicio<input required type="datetime-local" value={data.inicio} onChange={(event) => setField("inicio", event.target.value)} /></label><label>Fin<input type="datetime-local" value={data.fin} onChange={(event) => setField("fin", event.target.value)} /></label><label>Descripcion<textarea value={data.descripcion} onChange={(event) => setField("descripcion", event.target.value)} /></label></>;
    if (module === "M8") return <>{lineAndPress()}<label>Causa de vaciado<input required value={data.causa_vaciado} onChange={(event) => setField("causa_vaciado", event.target.value)} /></label><NumberField label="Duracion (min)" value={data.duracion_min} onChange={(value) => setField("duracion_min", value)} /><p className="inline-note">El vaciado requiere descartar aproximadamente 10 minutos de material y registrar la parada asociada en M6 si corresponde.</p></>;
    if (module === "M9") return <>{lineAndPress(true)}<NumberField label="Humedad de pasta (%)" value={data.humedad_pasta} onChange={(value) => setField("humedad_pasta", value)} /><NumberField label="Presion (kg/cm2)" value={data.presion} onChange={(value) => setField("presion", value)} /><NumberField label="Humedad residual (%)" value={data.humedad_residual} onChange={(value) => setField("humedad_residual", value)} /></>;
    return <><label>Linea<select value={data.linea} onChange={(event) => changeLine(event.target.value)}><option value="L6">L6</option><option value="L7">L7</option></select></label><label>Formato<select value={data.formato} onChange={(event) => setField("formato", event.target.value)}>{formats.map((format) => <option key={format}>{format}</option>)}</select></label><section className="thickness"><h3>Espesores: grilla 3x3 por cavidad</h3>{pressesByLine[data.linea].map((press) => <section className="press-grid" key={press}><h4>{press}</h4>{[1, 2].map((cavity) => <fieldset key={cavity}><legend>Cavidad {cavity}</legend><div>{Array.from({ length: 9 }, (_, index) => <label key={index}>S{index + 1}<input required aria-label={`${press} cavidad ${cavity} sector ${index + 1}`} type="number" step="0.01" value={data[inputId(press, cavity, index + 1)] ?? ""} onChange={(event) => setField(inputId(press, cavity, index + 1), event.target.value)} /></label>)}</div></fieldset>)}</section>)}</section></>;
  }

  return <main><section className="panel"><p className="eyebrow">F3 · Prensas</p><h1>Control de Proceso</h1><p className="subtitle">Preparacion de Pasta</p>{!token ? <form onSubmit={login}><label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label><button type="submit">Iniciar sesion</button></form> : <section className="forms"><h2>Operacion y formularios</h2><div className="form-actions">{["m1", "m2", "m3", "m6", "m8", "m9", "m10"].map((formModule) => <button key={formModule} type="button" onClick={() => printForm(formModule)}>Imprimir {formModule.toUpperCase()}</button>)}<button type="button" onClick={loadDashboard}>Actualizar dashboard</button></div>{dashboard && <section className="dashboard"><h2>Dashboard</h2><p>Ultimo recalculo: {dashboard.ultimo_recalculo ?? "Sin recalculo"}</p>{dashboard.hechos.map((fact) => <article key={`${fact.fecha_operativa}-${fact.turno}-${fact.contexto}`}><strong>{fact.fecha_operativa} · {fact.turno} · {fact.contexto}</strong><pre>{JSON.stringify(fact.metricas, null, 2)}</pre></article>)}</section>}<form className="operational" onSubmit={submitRecord}><h2>Registro operativo</h2><label>Modulo<select value={module} onChange={(event) => changeModule(event.target.value)}>{["M1", "M2", "M3", "M6", "M8", "M9", "M10"].map((item) => <option key={item}>{item}</option>)}</select></label>{commonFields()}{moduleFields()}<button type="submit">Guardar {module}</button></form><section className="offline"><h2>Sincronizacion offline</h2><button type="button" onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button>{pending.map((row) => <p key={row.id}>{row.module.toUpperCase()}: {row.status} {row.error}</p>)}</section></section>}<p className="message" role="status">{message}</p></section></main>;
}

function NumberField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label>{label}<input required type="number" step="any" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
