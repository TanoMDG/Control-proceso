import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-test-password";

async function login(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Usuario").fill(username);
  await page.getByLabel("Contrasena").fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesion" }).click();
  await expect(page.getByText("Sesion iniciada.")).toBeVisible();
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

test("real credentials expose role and remote navigation boundaries", async ({ page }) => {
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
});

test("M1, M2, M3, and M6 persist through the molienda UI", async ({ page }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").fill("1");
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
  await save(page, "M8");

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

test("offline IndexedDB survives reload, reconnects, and retries idempotently", async ({ page, context }) => {
  await login(page, "e2e-molienda");
  await operation(page);
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await context.setOffline(true);
  await page.getByLabel("Box activo (1, 2, 3 o 6)").fill("2");
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

test("two real sessions create a persisted stale-revision conflict", async ({ browser }) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  const pageA = await first.newPage();
  const pageB = await second.newPage();
  await login(pageA, "e2e-molienda");
  await operation(pageA);
  await pageA.getByLabel("Box activo (1, 2, 3 o 6)").fill("3");
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
  await expect(supervisor.getByText("registro_operativo")).toBeVisible();
});

test("the production service worker serves the cached shell offline", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Preparacion de Pasta" })).toBeVisible();
});
