import { expect, test, type Page } from "@playwright/test";

type Identity = { role: "CARGA" | "SUPERVISION" | "ADMIN"; sector: string; remote?: boolean };

function tokenFor(identity: Identity) {
  const payload = Buffer.from(JSON.stringify({ role: identity.role, sector: identity.sector, remote: Boolean(identity.remote) })).toString("base64url");
  return `header.${payload}.signature`;
}

async function mockApi(page: Page, identity: Identity) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/login")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ access_token: tokenFor(identity) }) });
      return;
    }
    if (url.pathname.endsWith("/kpi")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ultimo_recalculo: null, hechos: [] }) });
      return;
    }
    if (url.pathname.endsWith("/kpi/pareto-paradas")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ultimo_recalculo: null, pareto: [] }) });
      return;
    }
    if (url.pathname.endsWith("/laboratorio/configuracion")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ configuraciones: [], mensaje_configuracion: "Pendiente de configuracion" }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Usuario").fill("operador");
  await page.getByLabel("Contrasena").fill("clave-de-prueba");
  await page.getByRole("button", { name: "Iniciar sesion" }).click();
}

test("CARGA Laboratorio sees only its sector workflow", async ({ page }) => {
  await mockApi(page, { role: "CARGA", sector: "Laboratorio" });
  await login(page);
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "Operacion e historial" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Laboratorio P21/P22" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Supervision" })).toHaveCount(0);
  await expect(nav.getByRole("button", { name: "Administracion" })).toHaveCount(0);
  await nav.getByRole("button", { name: "Laboratorio P21/P22" }).click();
  await expect(page.getByRole("heading", { name: "Laboratorio" })).toBeVisible();
  await page.getByRole("button", { name: "Actualizar configuracion" }).click();
  await expect(page.getByText("Pendiente de configuracion")).toBeVisible();
});

test("CARGA Molienda does not receive laboratory or supervision navigation", async ({ page }) => {
  await mockApi(page, { role: "CARGA", sector: "Molienda" });
  await login(page);
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "Trazabilidad" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Laboratorio P21/P22" })).toHaveCount(0);
  await expect(nav.getByRole("button", { name: "Supervision" })).toHaveCount(0);
  await nav.getByRole("button", { name: "Operacion e historial" }).click();
  await expect(page.getByLabel("Modulo")).toHaveValue("M1");
});

test("supervision receives exception workflows but not administration", async ({ page }) => {
  await mockApi(page, { role: "SUPERVISION", sector: "Molienda" });
  await login(page);
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "Supervision" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Administracion" })).toHaveCount(0);
  await nav.getByRole("button", { name: "Supervision" }).click();
  await expect(page.getByRole("heading", { name: "Supervision" })).toBeVisible();
});

test("ADMIN receives administration navigation", async ({ page }) => {
  await mockApi(page, { role: "ADMIN", sector: "Administracion" });
  await login(page);
  await page.getByRole("navigation", { name: "Navegacion principal" }).getByRole("button", { name: "Administracion" }).click();
  await expect(page.getByRole("heading", { name: "Administracion" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear catalogo" })).toBeVisible();
});

test("remote consultation is restricted to the KPI dashboard", async ({ page }) => {
  await mockApi(page, { role: "CARGA", sector: "Remoto", remote: true });
  await login(page);
  const nav = page.getByRole("navigation", { name: "Navegacion principal" });
  await expect(nav.getByRole("button", { name: "Dashboard KPI" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Operacion e historial" })).toHaveCount(0);
  await expect(nav.getByRole("button", { name: "Laboratorio P21/P22" })).toHaveCount(0);
  await expect(nav.getByRole("button", { name: "Administracion" })).toHaveCount(0);
  await nav.getByRole("button", { name: "Dashboard KPI" }).click();
  await page.getByRole("button", { name: "Actualizar KPI" }).click();
  await expect(page.getByText("No hay hechos para el alcance seleccionado.")).toBeVisible();
});
