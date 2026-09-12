import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
type Sieve = { id: string; codigo: string; torre: string; descripcion: string };
type Configuration = { id: string; punto: { id: string; codigo: string; descripcion: string }; determinacion: { codigo: string; descripcion: string; tipo_resultado: "NUMERICO" | "GRANULOMETRIA" }; unidad: { codigo: string }; id_limite: string | null; frecuencias: unknown[]; tamices: Sieve[] };
type Agenda = { agenda: Array<{ id_configuracion: string; id_punto: string; esperado_en: string; vence_en: string; cumplido: boolean }>; cumplimiento: { esperados: number; realizados: number; porcentaje: number | null }; mensaje_configuracion: string | null };

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada.");
  const [pending, setPending] = useState<PendingRecord[]>([]);
  const [configuration, setConfiguration] = useState<Configuration[]>([]);
  const [configurationMessage, setConfigurationMessage] = useState<string | null>(null);
  const [pointId, setPointId] = useState("");
  const [shift, setShift] = useState("ACTUAL");
  const [values, setValues] = useState<Record<string, string>>({});
  const [sieveValues, setSieveValues] = useState<Record<string, string>>({});
  const [mua, setMua] = useState("");
  const [stock, setStock] = useState("");
  const [processRecord, setProcessRecord] = useState("");
  const [silo, setSilo] = useState("");
  const [product, setProduct] = useState("");
  const [agenda, setAgenda] = useState<Agenda | null>(null);

  async function request(route: string, payload?: Record<string, unknown>, method: "GET" | "POST" | "PUT" = "GET") {
    const response = await fetch(`${apiUrl}${route}`, { method, headers: { Authorization: `Bearer ${token}`, ...(payload ? { "Content-Type": "application/json" } : {}) }, body: payload ? JSON.stringify(payload) : undefined });
    if (!response.ok) throw Object.assign(new Error(await response.text()), { status: response.status });
    return response.json();
  }

  async function loadConfiguration() {
    try {
      const data = await request("/laboratorio/configuracion") as { configuraciones: Configuration[]; mensaje_configuracion: string | null };
      setConfiguration(data.configuraciones);
      setConfigurationMessage(data.mensaje_configuracion);
      if (!pointId && data.configuraciones[0]) setPointId(data.configuraciones[0].punto.id);
    } catch (error) { setMessage(`No fue posible cargar configuracion P21: ${String(error)}`); }
  }

  useEffect(() => {
    if (!token) return;
    void loadConfiguration();
    void listPending().then(setPending);
    const online = async () => { await synchronize(token, apiUrl); setPending(await listPending()); };
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request("/auth/login", { username, password }, "POST") as { access_token: string };
      sessionStorage.setItem("access_token", result.access_token); setToken(result.access_token); setMessage("Sesion iniciada.");
    } catch { setMessage("No fue posible iniciar sesion. Verifique sus credenciales."); }
  }

  const selected = configuration.filter((item) => item.punto.id === pointId);
  const points = Array.from(new Map(configuration.map((item) => [item.punto.id, item.punto])).values());

  async function saveAnalysis(event: FormEvent) {
    event.preventDefault();
    const now = new Date();
    const resultados = selected.filter((item) => item.determinacion.tipo_resultado === "NUMERICO" && values[item.id]?.trim()).map((item) => ({ id_configuracion: item.id, valor: values[item.id] }));
    const granulometria = selected.filter((item) => item.determinacion.tipo_resultado === "GRANULOMETRIA").flatMap((item) => item.tamices.filter((mesh) => sieveValues[`${item.id}:${mesh.id}`]?.trim()).map((mesh) => ({ id_configuracion: item.id, id_tamiz: mesh.id, valor: sieveValues[`${item.id}:${mesh.id}`] })));
    const payload = { client_uuid: crypto.randomUUID(), id_punto: pointId, fecha_operativa: now.toISOString().slice(0, 10), turno_codigo: shift, instante_muestreo: now.toISOString(), id_mua: mua || null, id_registro_stock: stock || null, id_registro_proceso: processRecord || null, silo: silo ? Number(silo) : null, id_producto: product || null, resultados, granulometria };
    try {
      await request("/laboratorio/analisis", payload, "POST"); setValues({}); setSieveValues({}); setMessage("P21 registrado con determinaciones configuradas.");
    } catch (error) {
      const code = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
      if (code && code < 500) { setMessage(`P21 no se guardo: ${String(error)}`); return; }
      await savePending({ ...makePending(payload.client_uuid, "m17", payload, navigator.onLine, String(error)), route: "/laboratorio/analisis", method: "POST" });
      setPending(await listPending()); setMessage("P21 quedo en cola local para sincronizar.");
    }
  }

  async function loadAgenda() {
    const end = new Date(); const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
    try { setAgenda(await request(`/laboratorio/agenda?desde=${encodeURIComponent(start.toISOString())}&hasta=${encodeURIComponent(end.toISOString())}${pointId ? `&id_punto=${pointId}` : ""}`) as Agenda); }
    catch (error) { setMessage(`No fue posible cargar P22: ${String(error)}`); }
  }

  return <main><section className="panel"><p className="eyebrow">F7 · M17 Laboratorio</p><h1>Control de Proceso</h1><p className="subtitle">P21 Analisis y P22 agenda de muestreo</p>{!token ? <form onSubmit={login}><label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label><button>Iniciar sesion</button></form> : <section className="forms"><div className="form-actions"><button type="button" onClick={loadConfiguration}>Actualizar configuracion</button><button type="button" onClick={loadAgenda}>Actualizar P22 (ultimas 24 h)</button><button type="button" onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button></div>{configurationMessage && <p className="warning">{configurationMessage}</p>}<section className="traceability"><h2>P21 · Analisis de laboratorio</h2><p className="inline-note">Humedad, residuo, hierro, densidad, fluidez y resistencias se muestran solo si ADMIN los configuro para el punto. La torre exige exactamente los tamices configurados.</p><form onSubmit={saveAnalysis}><label>Punto de muestreo<select value={pointId} onChange={(event) => { setPointId(event.target.value); setValues({}); setSieveValues({}); }} disabled={!points.length} required><option value="">Seleccione un punto</option>{points.map((point) => <option key={point.id} value={point.id}>{point.codigo} · {point.descripcion}</option>)}</select></label><label>Turno<input value={shift} onChange={(event) => setShift(event.target.value)} required /></label>{selected.filter((item) => item.determinacion.tipo_resultado === "NUMERICO").map((item) => <label key={item.id}>{item.determinacion.descripcion} ({item.unidad.codigo})<input inputMode="decimal" value={values[item.id] ?? ""} onChange={(event) => setValues({ ...values, [item.id]: event.target.value })} /></label>)}{selected.filter((item) => item.determinacion.tipo_resultado === "GRANULOMETRIA").map((item) => <fieldset className="thickness" key={item.id}><legend>{item.determinacion.descripcion} · {item.tamices[0]?.torre ?? "torre sin configurar"}</legend>{item.tamices.map((mesh) => <label key={mesh.id}>{mesh.codigo} · {mesh.descripcion}<input inputMode="decimal" value={sieveValues[`${item.id}:${mesh.id}`] ?? ""} onChange={(event) => setSieveValues({ ...sieveValues, [`${item.id}:${mesh.id}`]: event.target.value })} /></label>)}</fieldset>)}<fieldset className="thickness"><legend>Vinculos de trazabilidad opcionales</legend><label>MUA<input value={mua} onChange={(event) => setMua(event.target.value)} placeholder="UUID MUA" /></label><label>Registro de stock M3<input value={stock} onChange={(event) => setStock(event.target.value)} placeholder="UUID registro" /></label><label>Registro de proceso<input value={processRecord} onChange={(event) => setProcessRecord(event.target.value)} placeholder="UUID registro" /></label><label>Silo<input type="number" min="1" max="16" value={silo} onChange={(event) => setSilo(event.target.value)} /></label><label>Producto<input value={product} onChange={(event) => setProduct(event.target.value)} placeholder="UUID catalogo producto" /></label></fieldset><button disabled={!pointId || !!configurationMessage}>Guardar analisis configurado</button></form></section><section className="dashboard"><h2>P22 · Agenda y cumplimiento</h2>{agenda ? <><p>{agenda.cumplimiento.realizados}/{agenda.cumplimiento.esperados} controles realizados{agenda.cumplimiento.porcentaje !== null ? ` (${agenda.cumplimiento.porcentaje}%)` : ""}.</p>{agenda.mensaje_configuracion && <p className="warning">{agenda.mensaje_configuracion}</p>}<div className="agenda">{agenda.agenda.map((item) => <article key={`${item.id_configuracion}:${item.esperado_en}`}><strong>{item.cumplido ? "Cumplido" : "Pendiente"}</strong><span>{new Date(item.esperado_en).toLocaleString()}</span></article>)}</div></> : <p className="inline-note">Consulte la agenda para ver los controles esperados por frecuencia configurada. Las ausencias reducen cumplimiento; no crean analisis ni desvios ficticios.</p>}</section><section className="offline"><h2>Cola offline</h2><p>{pending.length ? pending.map((item) => `${item.module}: ${item.status}`).join(" · ") : "Sin pendientes."}</p></section></section>}<p className="message">{message}</p></section></main>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
