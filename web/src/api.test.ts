import { afterEach, describe, expect, it, vi } from "vitest";
import {
  chat,
  confirmEntry,
  getHealth,
  getLedger,
  getSchemes,
  pickRun,
  sell,
  submitClaim,
  type RunRecord,
  type SellData,
} from "./api";
import { frameableUrl, rupees, safeHref } from "./format";
import { docLabel, reasonLabel, translations } from "./i18n";

afterEach(() => vi.unstubAllGlobals());

const down = () => vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
const reply = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

describe("offline sample", () => {
  it("serves bundled data only when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", down());
    expect((await getHealth()).mode).toBe("mock");
    expect((await getLedger()).entries.length).toBeGreaterThan(0);
    expect((await getSchemes()).schemes.length).toBeGreaterThan(0);
  });

  it("surfaces an HTTP error from a reachable backend instead of hiding it with sample data", async () => {
    vi.stubGlobal("fetch", reply(409, { detail: "I cannot answer this one myself" }));
    await expect(getSchemes()).rejects.toThrow("I cannot answer this one myself");
  });

  it("treats a static host's 404 for a backend path as no backend, not as a failure", async () => {
    vi.stubGlobal("fetch", reply(404, {}));
    expect((await getHealth()).mode).toBe("mock");
  });

  it("reports live or replay from the backend itself", async () => {
    vi.stubGlobal("fetch", reply(200, { status: "ok", tinyfish_mode: "replay" }));
    expect((await getHealth()).mode).toBe("replay");
    vi.stubGlobal("fetch", reply(200, { status: "ok", tinyfish_mode: "live" }));
    expect((await getHealth()).mode).toBe("live");
  });

  it("answers the sample sell question with sources for every price line", async () => {
    vi.stubGlobal("fetch", down());
    const r = await sell("wheat", 20, "farmer_demo_1");
    const d = r.data as SellData;
    expect(r.status).toBe("answered");
    expect(d.options.length).toBe(6);
    expect(r.evidence.length).toBe(d.options.length + 1); // one per price line plus the MSP source
    expect(d.options[0].mandi).toBe(d.best.mandi);
  });

  it("answers a dose question in the sample with a hand-off and nothing else", async () => {
    vi.stubGlobal("fetch", down());
    const r = await chat("Chlorpyrifos kitna ml dalu?");
    expect(r.status).toBe("escalated");
    expect(r.data).toEqual({});
    expect(r.evidence).toEqual([]);
    expect(r.ticket_id).toBeTruthy();
  });

  it("moves Rs Unlocked when a sample entry is confirmed", async () => {
    vi.stubGlobal("fetch", down());
    const before = await getLedger();
    const entry = before.entries.find((e) => !e.confirmed);
    expect(entry).toBeTruthy();
    await confirmEntry(entry!.id);
    const after = await getLedger();
    expect(after.total_rs).toBe(before.total_rs + entry!.amount_rs);
    expect(after.projected_rs).toBe(before.projected_rs - entry!.amount_rs);
  });
});

describe("claim upload", () => {
  it("sends the photos and the phone location as multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ claim_id: "c1" })));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["x"], "field.jpg", { type: "image/jpeg" });
    await submitClaim({
      farmerId: "f1", crop: "wheat", event: "hail", eventDate: "2026-10-23", files: [file],
      deviceLocation: { lat: 28.98, lon: 77.7 },
    });
    const [url, init] = fetchMock.mock.calls[0];
    const form = init.body as FormData;
    expect(url).toBe("/api/claim/photos");
    expect(form.get("farmer_id")).toBe("f1");
    expect(form.get("device_lat")).toBe("28.98");
    expect((form.getAll("files")[0] as File).name).toBe("field.jpg");
  });

  it("omits the location when the farmer did not share it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ claim_id: "c1" })));
    vi.stubGlobal("fetch", fetchMock);
    await submitClaim({ farmerId: "f1", crop: "wheat", event: "hail", eventDate: "2026-10-23", files: [], deviceLocation: null });
    expect((fetchMock.mock.calls[0][1].body as FormData).has("device_lat")).toBe(false);
  });
});

describe("pickRun", () => {
  const run = (id: string, kind: RunRecord["kind"], created_at: string): RunRecord => ({
    id, kind, status: "RUNNING", target: "g", streaming_url: null, video_url: null, steps: null,
    mode: "live", created_at, updated_at: created_at,
  });
  const t0 = Date.parse("2026-10-24T10:00:10Z");

  it("finds the newest agent run started since the question was asked", () => {
    const runs = [
      run("old", "agent", "2026-10-24T09:00:00Z"),
      run("fetch", "fetch", "2026-10-24T10:00:11Z"),
      run("a", "agent", "2026-10-24T10:00:11Z"),
      run("b", "agent", "2026-10-24T10:00:14Z"),
    ];
    expect(pickRun(runs, t0)?.id).toBe("b");
  });

  it("ignores runs from before the question and non-agent calls", () => {
    expect(pickRun([run("old", "agent", "2026-10-24T09:00:00Z"), run("f", "fetch", "2026-10-24T10:00:12Z")], t0)).toBeNull();
    expect(pickRun([], t0)).toBeNull();
  });

  it("allows a couple of seconds of clock skew between phone and server", () => {
    expect(pickRun([run("a", "agent", "2026-10-24T10:00:09Z")], t0)?.id).toBe("a");
  });
});

describe("format", () => {
  it("groups rupees the Indian way", () => {
    expect(rupees(1234567)).toBe("₹12,34,567");
    expect(rupees(0)).toBe("₹0");
    expect(rupees(-1500)).toBe("-₹1,500");
  });
  it("only frames https live views and only links http(s)", () => {
    expect(frameableUrl("https://tf.example/stream")).toBe("https://tf.example/stream");
    for (const bad of ["http://tf.example", "javascript:alert(1)", "data:text/html,x", "", null, undefined, "not a url"]) {
      expect(frameableUrl(bad)).toBeNull();
    }
    expect(safeHref("https://a.example")).toBe("https://a.example");
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref(null)).toBeUndefined();
  });
});

describe("translations", () => {
  it("Hindi has every English key and no empty strings", () => {
    expect(Object.keys(translations.hi).sort()).toEqual(Object.keys(translations.en).sort());
    expect(Object.values(translations.hi).every((v) => v.length > 0)).toBe(true);
  });
  it("labels the documents and gate reasons the backend sends, and passes unknown ones through", () => {
    const t = (k: keyof typeof translations.en) => translations.en[k];
    expect(docLabel(t, "land_record")).toBe("Land record");
    expect(docLabel(t, "something_new")).toBe("something_new");
    expect(reasonLabel(t, "dose_question")).toMatch(/chemical/);
    expect(reasonLabel(t, "brand_new_code")).toBe("brand_new_code");
  });
});
