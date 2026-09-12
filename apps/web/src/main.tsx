import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { listPending, makePending, savePending, synchronize, type PendingRecord } from "./offline";
import { registerServiceWorker } from "./pwa";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
type Role = "CARGA" | "SUPERVISION" | "ADMIN";
type Session = { role: Role; sector: string; remote: boolean };
type Configuration = { id: string; punto: { id: string; codigo: string; descripcion: string }; determinacion: { codigo: string; descripcion: string; tipo_resultado: "NUMERICO" | "GRANULOMETRIA" }; unidad: { codigo: string }; tamices: Array<{ id: string; codigo: string; descripcion: string }> };
type RecordRow = { id: string; modulo: string; estado: string; fecha_operativa: string; turno_codigo: string; revision: number; datos: Record<string, unknown> };

function decodeSession(token: string): Session | null {
  try {
    const claims = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (!["CARGA", "SUPERVISION", "ADMIN"].includes(claims.role)) return null;
    return { role: claims.role, sector: claims.sector ?? "", remote: Boolean(claims.remote) };
  } catch { return null; }
}

function today() { return new Date().toISOString().slice(0, 10); }
function now() { return new Date().toISOString(); }
function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [session, setSession] = useState<Session | null>(() => decodeSession(sessionStorage.getItem("access_token") ?? ""));
  const [page, setPage] = useState("inicio");
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada.");
  const [pending, setPending] = useState<PendingRecord[]>([]);

  async function request<T>(route: string, payload?: unknown, method: "GET" | "POST" | "PUT" | "PATCH" = "GET"): Promise<T> {
    const response = await fetch(`${apiUrl}${route}`, { method, headers: { Authorization: `Bearer ${token}`, ...(payload !== undefined ? { "Content-Type": "application/json" } : {}) }, body: payload === undefined ? undefined : JSON.stringify(payload) });
    if (!response.ok) throw Object.assign(new Error(await response.text()), { status: response.status });
    const contentType = response.headers.get("content-type") ?? "";
    return (contentType.includes("application/json") ? response.json() : undefined) as T;
  }

  useEffect(() => {
    if (!token) return;
    void listPending().then(setPending);
    const online = async () => { await synchronize(token, apiUrl); setPending(await listPending()); };
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await fetch(`${apiUrl}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      if (!result.ok) throw new Error();
      const { access_token } = await result.json() as { access_token: string };
      const identity = decodeSession(access_token);
      if (!identity) throw new Error();
      sessionStorage.setItem("access_token", access_token); setToken(access_token); setSession(identity); setPage("inicio"); setMessage("Sesion iniciada.");
    } catch { setMessage("No fue posible iniciar sesion. Verifique sus credenciales."); }
  }

  function logout() { sessionStorage.removeItem("access_token"); setToken(""); setSession(null); setPage("inicio"); setMessage("Sesion finalizada."); }

  if (!token || !session) return <main><section className="panel login"><p className="eyebrow">CONTROL DE PROCESO</p><h1>Preparacion de Pasta</h1><p className="subtitle">Acceso operativo con permisos por rol y sector</p><form onSubmit={login}><label>Usuario<input aria-label="Usuario" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label>Contrasena<input aria-label="Contrasena" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label><button>Iniciar sesion</button></form><p className="message" role="status">{message}</p></section></main>;

  const canSupervise = session.role !== "CARGA";
  const canAdmin = session.role === "ADMIN";
  const showOperations = !session.remote;
  const showLaboratory = !session.remote && (canSupervise || session.sector === "Laboratorio");
  const showMaintenance = !session.remote && (canSupervise || session.sector === "Mantenimiento");
  const showTraceability = !session.remote && (canSupervise || ["Molienda", "Prensas"].includes(session.sector));
  const nav = [
    ["inicio", "Inicio"], ["dashboard", "Dashboard KPI"],
    ...(showOperations ? [["operacion", "Operacion e historial"]] : []),
    ...(showLaboratory ? [["laboratorio", "Laboratorio P21/P22"]] : []),
    ...(showTraceability ? [["trazabilidad", "Trazabilidad"]] : []),
    ...(showMaintenance ? [["mantenimiento", "Mantenimiento M7"]] : []),
    ...(canSupervise && !session.remote ? [["supervision", "Supervision"]] : []),
    ...(canAdmin && !session.remote ? [["administracion", "Administracion"]] : []),
  ];

  return <main><section className="app-shell"><header className="app-header"><div><p className="eyebrow">CONTROL DE PROCESO</p><h1>Preparacion de Pasta</h1></div><div className="identity"><strong>{session.remote ? "CONSULTA REMOTA" : session.role}</strong><span>{session.sector}</span><button type="button" className="secondary" onClick={logout}>Cerrar sesion</button></div></header><nav aria-label="Navegacion principal">{nav.map(([id, label]) => <button type="button" key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>{label}</button>)}</nav><p className="message" role="status">{message}</p>{page === "inicio" && <Home session={session} pending={pending} onNavigate={setPage} />}{page === "dashboard" && <Dashboard request={request} supervise={canSupervise && !session.remote} setMessage={setMessage} />}{page === "operacion" && <Operations request={request} session={session} setMessage={setMessage} />}{page === "laboratorio" && <Laboratory request={request} setMessage={setMessage} />}{page === "trazabilidad" && <Traceability request={request} session={session} setMessage={setMessage} />}{page === "mantenimiento" && <Maintenance request={request} setMessage={setMessage} />}{page === "supervision" && <Supervision request={request} admin={canAdmin} setMessage={setMessage} />}{page === "administracion" && <Administration request={request} setMessage={setMessage} />}{!session.remote && <section className="offline"><strong>Sincronizacion local</strong><span>{pending.length} carga(s) pendiente(s)</span><button type="button" className="secondary" onClick={async () => { await synchronize(token, apiUrl); setPending(await listPending()); }}>Sincronizar pendientes</button></section>}</section></main>;
}

function Home({ session, pending, onNavigate }: { session: Session; pending: PendingRecord[]; onNavigate: (page: string) => void }) {
  const destination = session.remote ? "dashboard" : "operacion";
  return <section className="content"><h2>Area de trabajo</h2><p>{session.remote ? "Su perfil puede consultar exclusivamente el dashboard KPI." : `Rol ${session.role} asignado al sector ${session.sector}. Las acciones disponibles se limitan al permiso y alcance del servidor.`}</p><div className="cards"><article><strong>Permiso activo</strong><span>{session.remote ? "Consulta remota" : `${session.role} / ${session.sector}`}</span></article><article><strong>Cola offline</strong><span>{pending.length} pendiente(s)</span></article></div><button type="button" onClick={() => onNavigate(destination)}>{session.remote ? "Ver dashboard" : "Ir a la operacion"}</button></section>;
}

function Dashboard({ request, supervise, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; supervise: boolean; setMessage: (value: string) => void }) {
  const [data, setData] = useState<{ ultimo_recalculo: string | null; hechos: Array<{ fecha_operativa: string; turno: string; contexto: string; metricas: Record<string, unknown> }> } | null>(null);
  const [pareto, setPareto] = useState<Array<{ causa: string; duracion_horas: number }>>([]);
  async function load() {
    try {
      const kpi = await request<NonNullable<typeof data>>("/kpi");
      setData(kpi);
      if (supervise) setPareto((await request<{ pareto: typeof pareto }>("/kpi/pareto-paradas")).pareto);
    } catch (error) { setMessage(`No fue posible cargar KPI: ${errorText(error)}`); }
  }
  return <section className="content">
    <div className="section-heading"><div><h2>Dashboard KPI</h2><p>Hechos reconstruidos y fecha del ultimo recalculo.</p></div><div className="form-actions"><button type="button" onClick={load}>Actualizar KPI</button>{supervise && <button type="button" className="secondary" onClick={async () => { try { await request("/analitica/recalcular", {}, "POST"); await load(); setMessage("Recalculo analitico solicitado."); } catch (error) { setMessage(errorText(error)); } }}>Recalcular</button>}</div></div>
    {data && <><p className="inline-note">Ultimo recalculo: {data.ultimo_recalculo ?? "Sin ejecuciones"}</p><div className="result-list">{data.hechos.map((fact, index) => <article key={`${fact.fecha_operativa}-${index}`}><strong>{fact.fecha_operativa} · {fact.turno} · {fact.contexto}</strong><pre>{JSON.stringify(fact.metricas, null, 2)}</pre></article>)}{!data.hechos.length && <p>No hay hechos para el alcance seleccionado.</p>}</div>{supervise && <section><h3>Pareto de paradas</h3><div className="result-list">{pareto.map((item) => <article key={item.causa}><strong>{item.causa}</strong><span>{item.duracion_horas} h</span></article>)}</div></section>}</>}
  </section>;
}

const modulesBySector: Record<string, string[]> = { Molienda: ["M1", "M2", "M3", "M6"], Prensas: ["M8", "M9", "M10"] };
function operationsFor(session: Session) { return session.role === "CARGA" ? modulesBySector[session.sector] ?? [] : ["M1", "M2", "M3", "M6", "M8", "M9", "M10"]; }
function fieldsFor(module: string): Array<[string, string, string]> {
  const common: Array<[string, string, string]> = [];
  if (module === "M1") return [["box_activo", "Box activo (1, 2, 3 o 6)", "number"], ["humedad_verdes", "Humedad Verdes", "number"], ["residuo", "Residuo", "number"], ["aeroseparador", "Aeroseparador", "number"], ["temperatura_quemador", "Temperatura quemador (opcional)", "number"], ...common];
  if (module === "M2") return [["caudal_pasta", "Caudal de pasta", "number"], ["caudal_agua", "Caudal de agua", "number"], ["humedad_salida", "Humedad de salida", "number"]];
  if (module === "M3") return [["tipo_registro", "Tipo: lecho, ksider_rechazo o stock_silo", "text"], ["humedad", "Humedad (lecho)", "number"], ["temperatura", "Temperatura (lecho)", "number"], ["humedad_ksider", "Humedad K-Sider", "number"], ["segundos_pesada", "Segundos pesada K-Sider", "number"], ["silo", "Silo (stock)", "number"], ["altura_libre_m", "Altura libre (stock)", "number"], ["linea", "Linea (opcional L6/L7)", "text"]];
  if (module === "M6") return [["causa", "Causa", "text"], ["descripcion", "Descripcion (obligatoria para P12)", "text"], ["inicio", "Inicio ISO con zona horaria", "datetime-local"], ["fin", "Fin ISO con zona horaria (opcional)", "datetime-local"]];
  if (module === "M8") return [["linea", "Linea (L6 o L7)", "text"], ["prensa", "Prensa", "text"], ["causa_vaciado", "Causa de vaciado", "text"], ["duracion_min", "Duracion (min)", "number"]];
  if (module === "M9") return [["linea", "Linea (L6 o L7)", "text"], ["prensa", "Prensa", "text"], ["formato", "Codigo de formato", "text"], ["humedad_pasta", "Humedad pasta", "number"], ["presion", "Presion", "number"], ["humedad_residual", "Humedad residual", "number"]];
  return [["linea", "Linea (L6 o L7)", "text"], ["formato", "Codigo de formato", "text"], ["detalles", "Detalles JSON: prensa, cavidad, sector, espesor_mm", "textarea"]];
}

function Operations({ request, session, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; session: Session; setMessage: (value: string) => void }) {
  const modules = operationsFor(session); const [module, setModule] = useState(modules[0] ?? "M1"); const [values, setValues] = useState<Record<string, string>>({}); const [rows, setRows] = useState<RecordRow[]>([]); const [shift, setShift] = useState("ACTUAL");
  useEffect(() => { setModule(modules[0] ?? "M1"); setValues({}); }, [session.sector]);
  async function load() { try { setRows(await request<RecordRow[]>(`/registros/${module}?desde=${today()}&hasta=${today()}`)); } catch (error) { setMessage(`No fue posible cargar historial: ${errorText(error)}`); } }
  async function submit(event: FormEvent) { event.preventDefault(); try { const datos: Record<string, unknown> = {}; for (const [key, , type] of fieldsFor(module)) { const value = values[key]?.trim(); if (!value) continue; datos[key] = type === "number" ? Number(value) : type === "datetime-local" ? new Date(value).toISOString() : key === "detalles" ? JSON.parse(value) : value; } const payload = { client_uuid: crypto.randomUUID(), fecha_operativa: today(), turno_codigo: shift, instante_medicion: now(), datos, origen_dato: "digital_directo" }; await request(`/registros/${module.toLowerCase()}`, payload, "POST"); setValues({}); await load(); setMessage(`${module} registrado como borrador.`); } catch (error) { const payload = { client_uuid: crypto.randomUUID(), fecha_operativa: today(), turno_codigo: shift, instante_medicion: now(), datos: values, origen_dato: "digital_directo" }; if (!navigator.onLine) { await savePending({ ...makePending(payload.client_uuid, module.toLowerCase(), payload, errorText(error)), route: `/registros/${module.toLowerCase()}`, method: "POST" }); setMessage(`${module} quedo en cola local.`); } else setMessage(`No se pudo registrar ${module}: ${errorText(error)}`); } }
  async function action(row: RecordRow, name: "cerrar" | "validar" | "anular") { const comment = window.prompt(`Comentario para ${name}:`); if (!comment) return; try { await request(`/registros/${module.toLowerCase()}/${row.id}/${name}`, { comentario: comment }, "POST"); await load(); setMessage(`Registro ${name}.`); } catch (error) { setMessage(errorText(error)); } }
  if (!modules.length) return <section className="content"><h2>Operacion</h2><p>Su sector no tiene modulos operativos asignados.</p></section>;
  return <section className="content"><h2>Operacion e historial</h2><div className="split"><form onSubmit={submit}><label>Modulo<select value={module} onChange={(event) => { setModule(event.target.value); setValues({}); }}>{modules.map((item) => <option key={item}>{item}</option>)}</select></label><label>Turno<input value={shift} onChange={(event) => setShift(event.target.value)} required /></label>{fieldsFor(module).map(([key, label, type]) => <label key={key}>{label}{type === "textarea" ? <textarea value={values[key] ?? ""} onChange={(event) => setValues({ ...values, [key]: event.target.value })} rows={4} /> : <input type={type} step={type === "number" ? "any" : undefined} value={values[key] ?? ""} onChange={(event) => setValues({ ...values, [key]: event.target.value })} required={!label.includes("opcional") && !["humedad", "temperatura", "humedad_ksider", "segundos_pesada", "silo", "altura_libre_m", "linea", "fin"].includes(key)} />}</label>)}<button>Guardar {module}</button></form><section><div className="form-actions"><button type="button" onClick={load}>Actualizar historial</button><a href={`${apiUrl}/exportar?modulo=${module.toLowerCase()}`} target="_blank" rel="noreferrer">Imprimir formulario</a></div><div className="result-list">{rows.map((row) => <article key={row.id}><strong>{row.fecha_operativa} · {row.turno_codigo} · {row.estado}</strong><span>Revision {row.revision}</span><pre>{JSON.stringify(row.datos, null, 2)}</pre><div className="form-actions">{row.estado === "BORRADOR" && <button type="button" className="secondary" onClick={() => action(row, "cerrar")}>Cerrar</button>}{session.role !== "CARGA" && row.estado === "CERRADO" && <button type="button" className="secondary" onClick={() => action(row, "validar")}>Validar</button>}{session.role !== "CARGA" && row.estado !== "ANULADO" && <button type="button" className="danger" onClick={() => action(row, "anular")}>Anular</button>}</div></article>)}</div></section></div></section>;
}

function Laboratory({ request, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; setMessage: (value: string) => void }) {
  const [configuration, setConfiguration] = useState<Configuration[]>([]); const [point, setPoint] = useState(""); const [values, setValues] = useState<Record<string, string>>({}); const [agenda, setAgenda] = useState<unknown>(null);
  const points: Configuration["punto"][] = Array.from(new Map<string, Configuration["punto"]>(configuration.map((item) => [item.punto.id, item.punto])).values()); const selected = configuration.filter((item) => item.punto.id === point);
  async function load() { try { const response = await request<{ configuraciones: Configuration[]; mensaje_configuracion: string | null }>("/laboratorio/configuracion"); setConfiguration(response.configuraciones); setPoint((current) => current || response.configuraciones[0]?.punto.id || ""); if (response.mensaje_configuracion) setMessage(response.mensaje_configuracion); } catch (error) { setMessage(errorText(error)); } }
  async function save(event: FormEvent) { event.preventDefault(); const resultados = selected.filter((item) => item.determinacion.tipo_resultado === "NUMERICO" && values[item.id]).map((item) => ({ id_configuracion: item.id, valor: values[item.id] })); const granulometria = selected.filter((item) => item.determinacion.tipo_resultado === "GRANULOMETRIA").flatMap((item) => item.tamices.filter((sieve) => values[`${item.id}:${sieve.id}`]).map((sieve) => ({ id_configuracion: item.id, id_tamiz: sieve.id, valor: values[`${item.id}:${sieve.id}`] }))); const payload = { client_uuid: crypto.randomUUID(), id_punto: point, fecha_operativa: today(), turno_codigo: "ACTUAL", instante_muestreo: now(), resultados, granulometria }; try { await request("/laboratorio/analisis", payload, "POST"); setValues({}); setMessage("P21 registrado con determinaciones configuradas."); } catch (error) { const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0; if (!status || status >= 500) { await savePending({ ...makePending(payload.client_uuid, "m17", payload, errorText(error)), route: "/laboratorio/analisis", method: "POST" }); setMessage("P21 quedo en cola local para sincronizar."); } else setMessage(`P21 no se guardo: ${errorText(error)}`); } }
  return <section className="content"><div className="section-heading"><div><h2>Laboratorio</h2><p>P21 analisis y P22 agenda. Solo se exponen determinaciones configuradas por ADMIN.</p></div><div className="form-actions"><button type="button" onClick={load}>Actualizar configuracion</button><button type="button" className="secondary" onClick={async () => { try { setAgenda(await request(`/laboratorio/agenda?desde=${encodeURIComponent(new Date(Date.now() - 86400000).toISOString())}&hasta=${encodeURIComponent(now())}${point ? `&id_punto=${point}` : ""}`)); } catch (error) { setMessage(errorText(error)); } }}>Actualizar P22</button></div></div><form onSubmit={save}><label>Punto de muestreo<select value={point} onChange={(event) => { setPoint(event.target.value); setValues({}); }} required><option value="">Seleccione un punto</option>{points.map((item) => <option key={item.id} value={item.id}>{item.codigo} · {item.descripcion}</option>)}</select></label><div className="field-grid">{selected.map((item) => item.determinacion.tipo_resultado === "NUMERICO" ? <label key={item.id}>{item.determinacion.descripcion} ({item.unidad.codigo})<input inputMode="decimal" value={values[item.id] ?? ""} onChange={(event) => setValues({ ...values, [item.id]: event.target.value })} /></label> : <fieldset key={item.id}><legend>{item.determinacion.descripcion}</legend>{item.tamices.map((sieve) => <label key={sieve.id}>{sieve.codigo} · {sieve.descripcion}<input inputMode="decimal" value={values[`${item.id}:${sieve.id}`] ?? ""} onChange={(event) => setValues({ ...values, [`${item.id}:${sieve.id}`]: event.target.value })} required /></label>)}</fieldset>)}</div><button disabled={!point}>Guardar P21</button></form>{agenda !== null && <section><h3>Agenda P22</h3><pre>{JSON.stringify(agenda, null, 2)}</pre></section>}</section>;
}

function Traceability({ request, session, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; session: Session; setMessage: (value: string) => void }) {
  const [mua, setMua] = useState<Array<{ id: string; codigo: string; presencias_activas: Array<{ box: string; desde: string }>; orden_fifo: number | null }>>([]); const [muaId, setMuaId] = useState(""); const [box, setBox] = useState("");
  async function load() { try { const rows = await request<typeof mua>("/mua"); setMua(rows); } catch (error) { setMessage(`No fue posible cargar MUA: ${errorText(error)}`); } }
  async function place(event: FormEvent) { event.preventDefault(); try { await request("/trazabilidad/mua-box", { id_mua: muaId, box, desde: now(), certeza: "CONFIRMADA" }, "POST"); setBox(""); await load(); setMessage("Presencia MUA-box registrada."); } catch (error) { setMessage(errorText(error)); } }
  return <section className="content"><h2>Trazabilidad MUA</h2><p>La secuencia conserva periodos y certeza; no calcula proporciones ni toneladas.</p><div className="split"><section><button type="button" onClick={load}>Actualizar MUA y FIFO</button><div className="result-list">{mua.map((item) => <article key={item.id}><strong>{item.codigo}</strong><span>FIFO: {item.orden_fifo ?? "sin box"}</span>{item.presencias_activas.map((presence) => <span key={presence.box}>Box {presence.box} desde {presence.desde}</span>)}</article>)}</div></section><form onSubmit={place}><h3>M5 · Cargar MUA en box</h3><label>MUA<select value={muaId} onChange={(event) => setMuaId(event.target.value)} required><option value="">Seleccione una MUA</option>{mua.map((item) => <option key={item.id} value={item.id}>{item.codigo}</option>)}</select></label><label>Box<input value={box} onChange={(event) => setBox(event.target.value)} required /></label><button>Registrar presencia</button>{session.role !== "CARGA" && <p className="inline-note">M4 (creacion de MUA) requiere un preparador Palero vigente y se gestiona desde administracion de personas.</p>}</form></div></section>;
}

function Maintenance({ request, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; setMessage: (value: string) => void }) {
  const [equipment, setEquipment] = useState<Array<{ id: string; codigo: string; descripcion: string }>>([]); const [responsibles, setResponsibles] = useState<Array<{ id: string; apellido_nombre: string }>>([]); const [form, setForm] = useState({ equipment: "", responsible: "", type: "", description: "", shift: "ACTUAL" });
  async function load() { try { const [items, people] = await Promise.all([request<typeof equipment>("/mantenimiento/equipos"), request<{ responsables: typeof responsibles; mensaje_configuracion: string | null }>("/mantenimiento/responsables")]); setEquipment(items); setResponsibles(people.responsables); if (people.mensaje_configuracion) setMessage(people.mensaje_configuracion); } catch (error) { setMessage(errorText(error)); } }
  async function save(event: FormEvent) { event.preventDefault(); try { await request("/mantenimiento/registros", { client_uuid: crypto.randomUUID(), fecha_operativa: today(), turno_codigo: form.shift, inicio: now(), id_equipo: form.equipment, id_responsable: form.responsible, tipo: form.type, descripcion: form.description, campos_madirex: {} }, "POST"); setMessage("M7 registrado. Los campos Madirex son informativos."); } catch (error) { setMessage(errorText(error)); } }
  return <section className="content"><div className="section-heading"><div><h2>M7 · Mantenimiento</h2><p>Intervenciones, responsables vigentes y correlaciones auditadas.</p></div><button type="button" onClick={load}>Actualizar configuracion</button></div><form onSubmit={save}><div className="field-grid"><label>Equipo<select value={form.equipment} onChange={(event) => setForm({ ...form, equipment: event.target.value })} required><option value="">Seleccione equipo</option>{equipment.map((item) => <option key={item.id} value={item.id}>{item.codigo} · {item.descripcion}</option>)}</select></label><label>Responsable<select value={form.responsible} onChange={(event) => setForm({ ...form, responsible: event.target.value })} required><option value="">Seleccione responsable</option>{responsibles.map((item) => <option key={item.id} value={item.id}>{item.apellido_nombre}</option>)}</select></label><label>Tipo<input value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })} required /></label><label>Turno<input value={form.shift} onChange={(event) => setForm({ ...form, shift: event.target.value })} required /></label></div><label>Descripcion<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label><button disabled={!equipment.length || !responsibles.length}>Guardar M7</button></form></section>;
}

function Supervision({ request, admin, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; admin: boolean; setMessage: (value: string) => void }) {
  const [tab, setTab] = useState("desvios"); const [rows, setRows] = useState<unknown[]>([]);
  const routes: Record<string, string> = { desvios: "/desvios", conflictos: "/sincronizacion/conflictos", auditoria: "/auditoria", plc: "/plc/estado" };
  async function load() { try { setRows(await request<unknown[]>(routes[tab])); } catch (error) { setMessage(errorText(error)); } }
  return <section className="content"><h2>Supervision</h2><div className="tabbar">{Object.keys(routes).map((item) => <button type="button" className={tab === item ? "active" : ""} onClick={() => { setTab(item); setRows([]); }} key={item}>{item}</button>)}</div><div className="form-actions"><button type="button" onClick={load}>Actualizar {tab}</button>{tab === "plc" && <span className="inline-note">F6 es solo lectura. No hay escritura de PLC.</span>}</div><div className="result-list">{rows.map((row, index) => <article key={index}><pre>{JSON.stringify(row, null, 2)}</pre></article>)}</div>{admin && <p className="inline-note">ADMIN dispone además de la pestaña Administracion para configurar maestros y fuentes PLC.</p>}</section>;
}

function Administration({ request, setMessage }: { request: <T>(r: string, p?: unknown, m?: "GET" | "POST" | "PUT" | "PATCH") => Promise<T>; setMessage: (value: string) => void }) {
  const [tab, setTab] = useState("usuarios"); const [rows, setRows] = useState<unknown[]>([]); const [catalogType, setCatalogType] = useState("formato"); const [code, setCode] = useState(""); const [description, setDescription] = useState("");
  const routes: Record<string, string> = { usuarios: "/usuarios", personas: "/personas", roles: "/roles", limites: "/limites", equipos: "/mantenimiento/equipos", laboratorio: "/laboratorio/puntos-muestreo", plc: "/plc/configuracion" };
  async function load() { try { setRows(await request<unknown[]>(routes[tab])); } catch (error) { setMessage(errorText(error)); } }
  async function createCatalog(event: FormEvent) { event.preventDefault(); try { await request("/catalogos", { tipo: catalogType, codigo: code, descripcion: description, atributos: {} }, "POST"); setCode(""); setDescription(""); setMessage("Catalogo creado y auditado."); } catch (error) { setMessage(errorText(error)); } }
  return <section className="content"><h2>Administracion</h2><p>Los maestros no contienen valores industriales precargados. Toda alta y baja queda auditada.</p><div className="tabbar">{Object.keys(routes).map((item) => <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => { setTab(item); setRows([]); }}>{item}</button>)}</div><div className="split"><section><button type="button" onClick={load}>Consultar {tab}</button><div className="result-list">{rows.map((row, index) => <article key={index}><pre>{JSON.stringify(row, null, 2)}</pre></article>)}</div></section><form onSubmit={createCatalog}><h3>Alta de catalogo</h3><label>Tipo<input value={catalogType} onChange={(event) => setCatalogType(event.target.value)} required /></label><label>Codigo<input value={code} onChange={(event) => setCode(event.target.value)} required /></label><label>Descripcion<input value={description} onChange={(event) => setDescription(event.target.value)} required /></label><button>Crear catalogo</button></form></div></section>;
}

registerServiceWorker();
createRoot(document.getElementById("root")!).render(<App />);
