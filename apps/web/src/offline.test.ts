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
});
