import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));
vi.mock("@/api/client", () => ({ apiRequest: apiRequestMock }));

import { listAllPatientIds } from "@/api/patients";

const page = (ids: string[], total: number) => ({ patient_ids: ids, total, scope: "all" });
const ids = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => `P${String(from + i).padStart(3, "0")}`);

beforeEach(() => apiRequestMock.mockReset());

describe("listAllPatientIds", () => {
  it("never asks for more than the server's cap of 100 per page (a larger limit is a 422)", async () => {
    apiRequestMock.mockResolvedValueOnce(page(ids(1, 11), 10));
    await listAllPatientIds();
    expect(apiRequestMock.mock.calls[0][0]).toContain("limit=100");
  });

  it("walks every page until the reported total is reached", async () => {
    apiRequestMock.mockResolvedValueOnce(page(ids(1, 101), 106)).mockResolvedValueOnce(page(ids(101, 107), 106));
    const all = await listAllPatientIds();
    expect(all).toHaveLength(106);
    expect(apiRequestMock).toHaveBeenCalledTimes(2);
    expect(apiRequestMock.mock.calls[1][0]).toContain("offset=100");
  });

  it("stops on an empty page instead of looping when the server over-reports the total", async () => {
    apiRequestMock.mockResolvedValueOnce(page(ids(1, 4), 9999)).mockResolvedValue(page([], 9999));
    expect(await listAllPatientIds()).toHaveLength(3);
    expect(apiRequestMock).toHaveBeenCalledTimes(2);
  });
});
