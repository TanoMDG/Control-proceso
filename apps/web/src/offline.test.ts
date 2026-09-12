import { describe, expect, it } from "vitest";
import { makePending } from "./offline";

describe("offline queue contract", () => {
  it("preserves client UUID and marks disconnected records pending", () => {
    const record = makePending("device-uuid", "m1", { client_uuid: "device-uuid" }, false);
    expect(record).toMatchObject({ id: "device-uuid", module: "m1", status: "pendiente" });
  });
  it("surfaces failed online synchronization", () => {
    expect(makePending("id", "m2", {}, true, "422").status).toBe("error");
  });
  it("keeps an M10 grid payload idempotent while offline", () => {
    const payload = { client_uuid: "m10-device-uuid", datos: { linea: "L7", detalles: [{ prensa: "PH5000-1", cavidad: 1, sector: 1, espesor_mm: "7.10" }] } };
    expect(makePending("m10-device-uuid", "m10", payload, false).payload).toEqual(payload);
  });
  it("retains an F4 temporal endpoint for offline retry", () => {
    const record = { ...makePending("m5-device-uuid", "m5", { id_mua: "mua-id", box: "1" }, false), route: "/trazabilidad/mua-box", method: "POST" as const };
    expect(record).toMatchObject({ module: "m5", route: "/trazabilidad/mua-box", method: "POST", status: "pendiente" });
  });
  it("retains an M7 maintenance record and its idempotency UUID for retry", () => {
    const payload = { client_uuid: "m7-device-uuid", id_equipo: "equipment-id", id_responsable: "person-id", campos_madirex: { observacion: "informativo" } };
    const record = { ...makePending("m7-device-uuid", "m7", payload, false), route: "/mantenimiento/registros", method: "POST" as const };
    expect(record).toMatchObject({ module: "m7", route: "/mantenimiento/registros", status: "pendiente" });
    expect(record.payload).toEqual(payload);
  });
  it("retains an M17 laboratory analysis and its configured result payload for retry", () => {
    const payload = { client_uuid: "m17-device-uuid", id_punto: "point-id", resultados: [{ id_configuracion: "humidity-config", valor: "2.8" }] };
    const record = { ...makePending("m17-device-uuid", "m17", payload, false), route: "/laboratorio/analisis", method: "POST" as const };
    expect(record).toMatchObject({ module: "m17", route: "/laboratorio/analisis", status: "pendiente" });
    expect(record.payload).toEqual(payload);
  });
});
