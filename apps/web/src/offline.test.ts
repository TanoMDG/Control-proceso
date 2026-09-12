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
});
