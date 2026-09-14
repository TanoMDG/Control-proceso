import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-test-password";
const API_URL = "http://api_e2e:8000/api/v1";

async function login(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Usuario").fill(username);
  await page.getByLabel("Contrasena").fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesion" }).click();
  await expect(page.getByText("Sesion iniciada.")).toBeVisible();
}

async function authenticatedRequest<T>(page: Page, route: string, method = "GET", payload?: unknown): Promise<{ status: number; body: T }> {
  return page.evaluate(async ({ route, method, payload }) => {
    const token = sessionStorage.getItem("access_token");
    const response = await fetch(`http://api_e2e:8000/api/v1${route}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(payload === undefined ? {} : { "Content-Type": "application/json" }) },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
    return { status: response.status, body: await response.json() };
  }, { route, method, payload });
}

async function operation(page: Page) {
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Operacion e historial" }).click();
}

async function save(page: Page, module: string) {
  await page.getByRole("button", { name: `Guardar ${module}` }).click();
  await expect(page.getByText(`${module} registrado como borrador.`)).toBeVisible();
}

function m10Details() {
  return ["PH5000-1", "PH5000-2"].flatMap((prensa) => [1, 2].flatMap((cavidad) => Array.from({ length: 9 }, (_, index) => ({ prensa, cavidad, sector: index + 1, espesor_mm: 7.1 }))));
}

async function pendingRecord(page: Page) {
  return page.evaluate(async () => new Promise<unknown>((resolve, reject) => {
    const open = indexedDB.open("control-procesos-offline");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const request = db.transaction("registros").objectStore("registros").getAll();
      request.onerror = () => reject(request.error);
      request.onsuccess = () => { db.close(); resolve(request.result[0]); };
    };
  }));
}

test.describe.configure({ mode: "serial" });

test("real credentials expose role and remote navigation boundaries", async ({ page, browser }) => {
  await login(page, "e2e-laboratorio");
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "Laboratorio P21/P22" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Supervision" })).toHaveCount(0);
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-supervision");
  await expect(nav.getByRole("button", { name: "Supervision" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Administracion" })).toHaveCount(0);
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-admin");
  await expect(nav.getByRole("button", { name: "Administracion" })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-remoto");
  await expect(nav.getByRole("button", { name: "Dashboard KPI" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Operacion e historial" })).toHaveCount(0);
  await nav.getByRole("button", { name: "Dashboard KPI" }).click();
  await page.getByRole("button", { name: "Actualizar KPI" }).click();
  await expect(page.getByText("No hay hechos para el alcance seleccionado.")).toBeVisible();
  const rejected = await authenticatedRequest(page, "/registros/m1", "POST", { origen_dato: "digital_directo" });
  expect(rejected.status).toBe(403);
  const token = await page.evaluate(() => sessionStorage.getItem("access_token"));
  const directContext = await browser.newContext({ extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
  const directPage = await directContext.newPage();
  await directPage.goto(`${API_URL}/registros/m1`);
  await expect(directPage.getByText("Consulta remota solo puede acceder a GET /api/v1/kpi")).toBeVisible();
  await directContext.close();
});

test("v1.0.1 names the operational and administration screens", async ({ page }) => {
  await login(page, "e2e-molienda");
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "P02-P12 - Operacion e historial", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: "P01 - Inicio", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-admin");
  await expect(nav.getByRole("button", { name: "P17-P25 - Administracion", exact: true })).toBeVisible();
  await nav.getByRole("button", { name: "P17-P25 - Administracion", exact: true }).click();
  await expect(page.getByRole("heading", { name: "P17-P25 · Administracion", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "P25 · parametros", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "P25 · parametros", exact: true }).click();
  await page.getByRole("button", { name: "Consultar P25 · parametros", exact: true }).click();
  await expect(page.getByText("v1.0.1").first()).toBeVisible();
});

test("M1 offers only consumable boxes and surfaces the D01 warning flow", async ({ page }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  const box = page.getByLabel("Box activo (1, 2, 3 o 6)");
  await expect(box.locator("option")).toHaveText(["Seleccione box", "1", "2", "3", "6"]);
  await box.selectOption("6");
  await page.getByLabel("Humedad Verdes").fill("4.1");
  await page.getByLabel("Residuo").fill("1.7");
  await page.getByLabel("Aeroseparador").fill("3.2");
  await page.getByRole("button", { name: "Guardar M1" }).click();
  await expect(page.getByText("Advertencia D01 abierto.")).toBeVisible();
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  page.once("dialog", (dialog) => dialog.accept("Cierre M1 E2E"));
  await page.getByRole("button", { name: "Cerrar", exact: true }).first().click();
  await expect(page.getByText("Registro cerrar.")).toBeVisible();
});

test("supervision persists deviation lifecycle, correction audit, conflict, and dashboard data", async ({ page, browser }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").selectOption("6");
  await page.getByLabel("Humedad Verdes").fill("4.1");
  await page.getByLabel("Residuo").fill("1.7");
  await page.getByLabel("Aeroseparador").fill("3.2");
  await save(page, "M1");
  const records = await authenticatedRequest<Array<{ id: string; revision: number; datos: Record<string, unknown> }>>(page, "/registros/m1");
  expect(records.status).toBe(200);
  const record = records.body.find((item) => String(item.datos.humedad_verdes) === "4.1");
  expect(record).toBeTruthy();
  const deviations = await authenticatedRequest<Array<{ id: string; estado: string }>>(page, "/desvios");
  const deviation = deviations.body.find((item) => item.estado === "ABIERTO");
  expect(deviation).toBeTruthy();
  expect((await authenticatedRequest(page, `/desvios/${deviation!.id}/tratar`, "POST", { comentario: "Ajuste E2E" })).status).toBe(200);
  expect((await authenticatedRequest(page, `/desvios/${deviation!.id}/verificar`, "POST", { comentario: "Verificacion E2E" })).status).toBe(200);
  expect((await authenticatedRequest(page, `/registros/m1/${record!.id}/cerrar`, "POST", { comentario: "Cierre E2E" })).status).toBe(200);
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-supervision");
  expect((await authenticatedRequest(page, `/desvios/${deviation!.id}/cerrar`, "POST", { comentario: "Cierre supervisado E2E" })).status).toBe(200);
  const corrected = await authenticatedRequest<{ revision: number }>(page, `/registros/m1/${record!.id}`, "PUT", { revision: record!.revision + 1, motivo_correccion: "Lectura verificada E2E", datos: { ...record!.datos, humedad_verdes: 2.9 } });
  expect(corrected.status).toBe(200);
  const audit = await authenticatedRequest<Array<{ accion: string; motivo: string | null }>>(page, "/auditoria");
  expect(audit.body).toEqual(expect.arrayContaining([expect.objectContaining({ accion: "CORRECCION", motivo: "Lectura verificada E2E" })]));
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Dashboard KPI" }).click();
  await page.getByRole("button", { name: "Recalcular" }).click();
  await expect(page.getByText("Recalculo analitico solicitado.")).toBeVisible();
  await page.getByRole("button", { name: "Actualizar KPI" }).click();
  await expect(page.getByText(/humedad_verdes/)).toBeVisible();

  const stale = await browser.newPage();
  await login(stale, "e2e-molienda");
  const conflict = await authenticatedRequest(stale, `/registros/m1/${record!.id}`, "PUT", { revision: record!.revision + 1, datos: record!.datos });
  expect(conflict.status).toBe(409);
  await stale.close();
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Supervision" }).click();
  await page.getByRole("button", { name: "conflictos" }).click();
  await page.getByRole("button", { name: "Actualizar conflictos" }).click();
  await expect(page.getByText("registro_operativo").first()).toBeVisible();
});

test("administration persists master, limit, calendar, and PLC configuration", async ({ page }) => {
  await login(page, "e2e-admin");
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Administracion" }).click();
  await page.getByLabel("Tipo").fill("e2e-master");
  await page.getByLabel("Codigo").fill("E2E-MASTER-ACCEPTANCE");
  await page.getByLabel("Descripcion").fill("Maestro persistente E2E");
  await page.getByRole("button", { name: "Crear catalogo" }).click();
  await expect(page.getByText("Catalogo creado y auditado.")).toBeVisible();
  const catalog = await authenticatedRequest<Array<{ codigo: string }>>(page, "/catalogos/e2e-master");
  expect(catalog.body).toEqual(expect.arrayContaining([expect.objectContaining({ codigo: "E2E-MASTER-ACCEPTANCE" })]));

  expect((await authenticatedRequest(page, "/limites", "POST", { id: "E2E-LIM", variable: "Limite E2E", etapa: "E2E", unidad: "%", tipo_dato: "numero" })).status).toBe(201);
  expect((await authenticatedRequest(page, "/limites/E2E-LIM/versiones", "POST", { vigente_desde: "2020-01-01", valor_min: "1", valor_max: "2", operador_min: ">=", operador_max: "<=", nivel: "ADVERTENCIA", motivo_cambio: "Version E2E" })).status).toBe(201);
  const limits = await authenticatedRequest<Array<{ id_limite: string }>>(page, "/limites");
  expect(limits.body).toEqual(expect.arrayContaining([expect.objectContaining({ id_limite: "E2E-LIM" })]));
  expect((await authenticatedRequest(page, "/calendario", "POST", { fecha_operativa: "2026-09-12", turno_codigo: "08-16", programado: true, horas_programadas: "8", motivo: "Calendario E2E" })).status).toBe(201);
  const calendar = await authenticatedRequest<Array<{ motivo: string | null }>>(page, "/calendario?desde=2026-09-12&hasta=2026-09-12");
  expect(calendar.body).toEqual(expect.arrayContaining([expect.objectContaining({ motivo: "Calendario E2E" })]));
  const source = await authenticatedRequest<{ id: string }>(page, "/plc/configuracion", "POST", { nombre: "Fuente E2E", adaptador: "TEST_SIMULATOR", activo: true });
  expect(source.status).toBe(201);
  const tag = await authenticatedRequest<{ referencia_tag: string }>(page, `/plc/configuracion/${source.body.id}/tags`, "POST", { metrica: "medicion_e2e", referencia_tag: "E2E.TAG.01", unidad: "u", escala_factor: "1", escala_offset: "0", muestreo_segundos: 60, agregacion_segundos: 300, retencion_crudo_dias: 1, retencion_agregado_dias: 1, turno_codigo: "08-16", sector: "Molienda", valor_simulado_crudo: "1", calidad_simulada: "GOOD", activo: true });
  expect(tag.status).toBe(201);
  const sources = await authenticatedRequest<Array<{ id: string }>>(page, "/plc/configuracion");
  expect(sources.body).toEqual(expect.arrayContaining([expect.objectContaining({ id: source.body.id })]));
});

test("M1, M2, M3, and M6 persist through the molienda UI", async ({ page }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").selectOption("1");
  await page.getByLabel("Humedad Verdes").fill("2.8");
  await page.getByLabel("Residuo").fill("1.2");
  await page.getByLabel("Aeroseparador").fill("3.4");
  await save(page, "M1");

  await page.getByLabel("Modulo").selectOption("M2");
  await page.getByLabel("Caudal de pasta").fill("30");
  await page.getByLabel("Caudal de agua").fill("7500");
  await page.getByLabel("Humedad de salida").fill("5");
  await save(page, "M2");

  await page.getByLabel("Modulo").selectOption("M3");
  await page.getByLabel("Tipo: lecho, ksider_rechazo o stock_silo").fill("lecho");
  await page.getByLabel("Humedad (lecho)").fill("4");
  await page.getByLabel("Temperatura (lecho)").fill("300");
  await save(page, "M3");

  await page.getByLabel("Modulo").selectOption("M6");
  await page.getByLabel("Causa").fill("P01");
  await page.getByLabel("Descripcion (obligatoria para P12)").fill("Parada sintetica E2E");
  await page.getByLabel("Inicio ISO con zona horaria").fill("2026-09-12T08:00");
  await page.getByLabel("Fin ISO con zona horaria (opcional)").fill("2026-09-12T09:00");
  await save(page, "M6");
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  await expect(page.getByText("Parada sintetica E2E")).toBeVisible();
});

test("M8, M9, and M10 persist through the prensas UI", async ({ page }) => {
  await login(page, "e2e-prensas");
  await operation(page);
  await page.getByLabel("Modulo").selectOption("M8");
  await page.getByLabel("Linea (L6 o L7)").fill("L6");
  await page.getByLabel("Prensa").fill("PH Siti");
  await page.getByLabel("Causa de vaciado").fill("Limpieza E2E");
  await page.getByLabel("Duracion (min)").fill("10");
  await expect(page.getByLabel("Crear parada M6 asociada")).not.toBeChecked();
  await save(page, "M8");
  let m8 = await authenticatedRequest<Array<{ id: string; datos: Record<string, string> }>>(page, "/registros/m8");
  const withoutStop = m8.body.find((record) => record.datos.causa_vaciado === "Limpieza E2E");
  expect(withoutStop?.datos.id_parada_asociada).toBeUndefined();

  await page.getByLabel("Linea (L6 o L7)").fill("L6");
  await page.getByLabel("Prensa").fill("PH Siti");
  await page.getByLabel("Causa de vaciado").fill("Limpieza E2E con parada");
  await page.getByLabel("Duracion (min)").fill("10");
  await page.getByLabel("Crear parada M6 asociada").check();
  await save(page, "M8");
  m8 = await authenticatedRequest<Array<{ id: string; datos: Record<string, string> }>>(page, "/registros/m8");
  const withStop = m8.body.find((record) => record.datos.causa_vaciado === "Limpieza E2E con parada");
  expect(withStop?.datos.id_parada_asociada).toBeTruthy();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();
  await login(page, "e2e-admin");
  const stops = await authenticatedRequest<Array<{ id: string; datos: Record<string, string> }>>(page, "/registros/m6");
  expect(stops.body).toEqual(expect.arrayContaining([expect.objectContaining({ id: withStop?.datos.id_parada_asociada, datos: expect.objectContaining({ id_m8_asociado: withStop?.id }) })]));
  await page.getByRole("button", { name: "Cerrar sesion" }).click();
  await login(page, "e2e-prensas");
  await operation(page);
  await page.getByLabel("Modulo").selectOption("M9");

  await page.getByLabel("Linea (L6 o L7)").fill("L6");
  await page.getByLabel("Prensa").fill("PH Siti");
  await page.getByLabel("Codigo de formato").fill("E2E-64X64");
  await page.getByLabel("Humedad pasta").fill("20");
  await page.getByLabel("Presion").fill("230");
  await page.getByLabel("Humedad residual").fill("5");
  await save(page, "M9");

  await page.getByLabel("Modulo").selectOption("M10");
  await page.getByLabel("Linea (L6 o L7)").fill("L7");
  await page.getByLabel("Codigo de formato").fill("E2E-64X64");
  await page.getByLabel("Detalles JSON: prensa, cavidad, sector, espesor_mm").fill(JSON.stringify(m10Details()));
  await save(page, "M10");
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  await expect(page.getByText("PH5000-2").last()).toBeVisible();
});

test("M4, M5, M7, and M17 use persisted test masters", async ({ page }) => {
  await login(page, "e2e-supervision");
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Trazabilidad" }).click();
  await page.getByRole("button", { name: "Actualizar MUA y FIFO" }).click();
  await page.getByLabel("Componente").fill("Arcilla sintetica");
  await page.getByRole("button", { name: "Crear MUA" }).click();
  await expect(page.getByText("M4 registrado con identidad MUA.")).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-molienda");
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Trazabilidad" }).click();
  await page.getByRole("button", { name: "Actualizar MUA y FIFO" }).click();
  await page.getByLabel("MUA").selectOption({ index: 1 });
  await page.getByLabel("Box").fill("1");
  await page.getByRole("button", { name: "Registrar presencia" }).click();
  await expect(page.getByText("Presencia MUA-box registrada.")).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-mantenimiento");
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Mantenimiento M7" }).click();
  await page.getByRole("button", { name: "Actualizar configuracion" }).click();
  await page.getByLabel("Equipo").selectOption({ index: 1 });
  await page.getByLabel("Responsable").selectOption({ index: 1 });
  await page.getByLabel("Tipo").fill("PREVENTIVO");
  await page.getByLabel("Descripcion").fill("Mantenimiento sintetico E2E");
  await page.getByRole("button", { name: "Guardar M7" }).click();
  await expect(page.getByText("M7 registrado. Los campos Madirex son informativos.")).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesion" }).click();

  await login(page, "e2e-laboratorio");
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Laboratorio P21/P22" }).click();
  await page.getByRole("button", { name: "Actualizar configuracion" }).click();
  await page.getByLabel("Humedad sintetica (pct)").fill("3.2");
  await page.getByRole("button", { name: "Guardar P21" }).click();
  await expect(page.getByText("P21 registrado con determinaciones configuradas.")).toBeVisible();
});

test("CP24 hides a deactivated M4 preparer while retaining the historical trace", async ({ page }) => {
  const preparerName = "Palero historico CP24 E2E";
  await login(page, "e2e-admin");
  const person = await authenticatedRequest<{ id: string }>(page, "/personas", "POST", { legajo: "E2E-CP24-PALERO", apellido_nombre: preparerName });
  expect(person.status).toBe(201);
  expect((await authenticatedRequest(page, `/personas/${person.body.id}/puestos`, "POST", { puesto: "Palero", vigente_desde: "2020-01-01" })).status).toBe(201);

  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Trazabilidad" }).click();
  await page.getByRole("button", { name: "Actualizar MUA y FIFO" }).click();
  const preparer = page.getByLabel("Preparador M4");
  await expect(preparer.getByRole("option", { name: preparerName, exact: true })).toHaveCount(1);
  await preparer.selectOption(person.body.id);
  await page.getByLabel("Componente").fill("Arcilla CP24 E2E");
  await page.getByRole("button", { name: "Crear MUA" }).click();
  await expect(page.getByText("M4 registrado con identidad MUA.")).toBeVisible();
  const muas = await authenticatedRequest<Array<{ id: string; codigo: string; id_preparador: string }>>(page, "/mua");
  const mua = muas.body.find((item) => item.id_preparador === person.body.id);
  expect(mua).toBeTruthy();

  expect((await authenticatedRequest(page, `/personas/${person.body.id}`, "PATCH", { activo: false, fecha_baja: new Date().toISOString().slice(0, 10) })).status).toBe(200);
  await page.getByRole("button", { name: "Actualizar MUA y FIFO" }).click();
  await expect(preparer.getByRole("option", { name: preparerName, exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: `Ver trazabilidad ${mua!.codigo}` }).click();
  await expect(page.getByRole("heading", { name: `Trazabilidad historica ${mua!.codigo}` })).toBeVisible();
  await expect(page.getByText(`Preparador M4: ${preparerName}`)).toBeVisible();
});

test("offline IndexedDB survives reload, reconnects, and retries idempotently", async ({ page, context }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await context.setOffline(true);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").selectOption("2");
  await page.getByLabel("Humedad Verdes").fill("2.7");
  await page.getByLabel("Residuo").fill("1.1");
  await page.getByLabel("Aeroseparador").fill("3.3");
  await page.getByRole("button", { name: "Guardar M1" }).click();
  await expect(page.getByText("M1 quedo en cola local.")).toBeVisible();
  expect(await pendingRecord(page)).toBeTruthy();
  await page.reload();
  await expect(page.getByText("1 carga(s) pendiente(s)")).toBeVisible();
  await context.setOffline(false);
  await page.getByRole("button", { name: "Sincronizar pendientes" }).click();
  await expect(page.getByText("0 carga(s) pendiente(s)")).toBeVisible();
  await operation(page);
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  await expect(page.getByText('"2.7"')).toHaveCount(1);

  await page.getByRole("button", { name: "Sincronizar pendientes" }).click();
  await operation(page);
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  await expect(page.getByText('"2.7"')).toHaveCount(1);
});

test("CP60 offline out-of-range M1 retry creates one D01 event", async ({ page, context }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await expect(page.getByLabel("Box activo (1, 2, 3 o 6)")).toHaveCount(1);
  await context.setOffline(true);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").selectOption("6");
  await page.getByLabel("Humedad Verdes").fill("4.4");
  await page.getByLabel("Residuo").fill("1.1");
  await page.getByLabel("Aeroseparador").fill("3.3");
  await page.getByRole("button", { name: "Guardar M1" }).click();
  await expect(page.getByText("M1 quedo en cola local.")).toBeVisible();
  await context.setOffline(false);
  await page.getByRole("button", { name: "Sincronizar pendientes" }).click();
  await expect(page.getByText("0 carga(s) pendiente(s)")).toBeVisible();
  const records = await authenticatedRequest<Array<{ id: string; datos: Record<string, unknown> }>>(page, "/registros/m1");
  const retried = records.body.find((record) => String(record.datos.humedad_verdes) === "4.4" && String(record.datos.box_activo) === "6");
  expect(retried).toBeTruthy();
  const once = (await authenticatedRequest<Array<{ id_registro: string; id_desvio: string }>>(page, "/desvios")).body.filter((event) => event.id_registro === retried!.id && event.id_desvio === "D01");
  expect(once).toHaveLength(1);
  await page.getByRole("button", { name: "Sincronizar pendientes" }).click();
  const retriedAgain = (await authenticatedRequest<Array<{ id_registro: string; id_desvio: string }>>(page, "/desvios")).body.filter((event) => event.id_registro === retried!.id && event.id_desvio === "D01");
  expect(retriedAgain).toHaveLength(1);
});

test("two real sessions create a persisted stale-revision conflict", async ({ browser }) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  const pageA = await first.newPage();
  const pageB = await second.newPage();
  await login(pageA, "e2e-molienda");
  await operation(pageA);
  await pageA.getByLabel("Box activo (1, 2, 3 o 6)").selectOption("3");
  await pageA.getByLabel("Humedad Verdes").fill("2.6");
  await pageA.getByLabel("Residuo").fill("1.3");
  await pageA.getByLabel("Aeroseparador").fill("3.5");
  await save(pageA, "M1");
  await login(pageB, "e2e-molienda");
  await operation(pageB);
  await pageB.getByRole("button", { name: "Actualizar historial" }).click();
  await pageB.getByRole("button", { name: "Editar" }).first().click();
  await pageB.getByLabel("Humedad Verdes").fill("2.9");
  await pageB.getByRole("button", { name: "Guardar correccion M1" }).click();
  await expect(pageB.getByText("M1 corregido.")).toBeVisible();

  await pageA.getByRole("button", { name: "Editar" }).first().click();
  await pageA.getByLabel("Humedad Verdes").fill("3.0");
  await pageA.getByRole("button", { name: "Guardar correccion M1" }).click();
  await expect(pageA.getByText(/Revision desactualizada; conflicto creado/)).toBeVisible();
  await first.close();
  await second.close();

  const supervisor = await browser.newPage();
  await login(supervisor, "e2e-supervision");
  await supervisor.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Supervision" }).click();
  await supervisor.getByRole("button", { name: "conflictos" }).click();
  await supervisor.getByRole("button", { name: "Actualizar conflictos" }).click();
  await expect(supervisor.getByText("registro_operativo").first()).toBeVisible();
});

test("the production service worker serves the cached shell offline", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Preparacion de Pasta" })).toBeVisible();
});
