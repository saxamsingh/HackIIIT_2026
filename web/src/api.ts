// Typed client for the KhetKaaj API. Types mirror backend/app/models.py (CLAUDE.md section 5).
// Every call falls back to src/mocks/*.json ONLY when the backend is unreachable (a network error).
// An HTTP error from a reachable backend is real and is thrown, never papered over with sample data.

import alertsMock from "./mocks/alerts.json";
import chatDoseMock from "./mocks/chat_dose.json";
import chatMenuMock from "./mocks/chat_menu.json";
import claimMock from "./mocks/claim.json";
import farmersMock from "./mocks/farmers.json";
import ledgerMock from "./mocks/ledger.json";
import runsMock from "./mocks/runs.json";
import schemesMock from "./mocks/schemes.json";
import sellMock from "./mocks/sell.json";

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/** live = real portals; replay = recorded fixtures; mock = backend unreachable, bundled sample data. */
export type Mode = "live" | "replay" | "mock";
export type Language = "hi" | "en" | "hinglish";

export interface Evidence {
  source_url: string;
  kind: "search" | "fetch" | "agent" | "monitor" | "replay" | "knowledge";
  title?: string | null;
  quote?: string | null;
  fetched_at: string;
  run_id?: string | null;
  assumed: boolean;
}
export interface Farmer {
  id: string;
  name: string;
  phone?: string | null;
  state: string;
  district: string;
  crops: string[];
  land_acres: number;
  category: "small" | "marginal" | "other";
  language: Language;
  documents: string[];
}
export interface GatedResponse {
  status: "answered" | "escalated" | "menu";
  language: Language;
  intent: "sell" | "subsidy" | "claim" | "advisory" | "unknown";
  reply: string;
  agent?: "sell" | "subsidy" | "claim" | "watch" | null;
  data: Record<string, any>;
  evidence: Evidence[];
  confidence: number;
  run_id?: string | null;
  ticket_id?: string | null;
  reasons: string[];
}
export interface MandiOption {
  mandi: string;
  modal_price: number;
  distance_km: number;
  transport_cost: number;
  net_price: number;
  distance_assumed: boolean;
  arrival_date: string | null;
}
export interface MspInfo {
  price_rs_per_qtl: number | null;
  marketing_season?: string;
  source_url?: string;
  quality?: string;
  difference_rs?: number;
  difference_pct?: number;
  below_msp?: boolean;
  note?: string;
}
export interface SellData {
  crop: string;
  district: string;
  quantity_qtl: number;
  options: MandiOption[];
  best: MandiOption;
  nearest: MandiOption;
  gain_rs: number;
  formula: string;
  msp: MspInfo;
  warnings: string[];
  assumptions: string[];
  rung: "fetch" | "agent";
  data_mode: "live" | "replay";
  ledger_entry_id?: string;
}
export interface SchemeSourceRecord {
  url: string;
  title: string;
  retrieved: string;
}

export interface SchemeCatalogItem {
  id: string;
  name: string;
  level: string;
  benefit: string;
  value_basis: string;
  apply_url: string;
  url_verified: boolean;
  deadline: string | null;
  eligibility: Record<string, unknown>;
  requires_documents: string[];
  requires_facts: string[];
  notes: string;
  sources: SchemeSourceRecord[];
  reviewed: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  discovered?: boolean;
}

export interface SchemeMatch {
  scheme_id: string;
  name: string;
  benefit: string;
  estimated_value_rs: number | null;
  eligible: boolean;
  missing_docs: string[];
  needs_info: string[];
  reasons: string[];
  deadline: string | null;
  apply_url: string;
  reviewed: boolean;
  packet_url: string | null;
  evidence: Evidence[];
}
export interface SchemesResponse {
  farmer_id: string;
  schemes: SchemeMatch[];
  confidence: number;
  requires_farmer_confirmation: boolean;
  note: string | null;
}
export interface ClaimResponse {
  claim_id: string;
  status: "draft";
  dossier_url: string;
  alert_id: string | null;
  intimation_deadline: string | null;
  warnings: string[];
  evidence: Evidence[];
  confidence: number;
}
export interface LedgerEntry {
  id: string;
  farmer_id: string;
  kind: "sell" | "subsidy" | "claim";
  amount_rs: number;
  formula: string;
  confirmed: boolean;
  created_at: string;
}
export interface LedgerResponse {
  farmer_id: string | null;
  total_rs: number;
  projected_rs: number;
  entries: LedgerEntry[];
}
export interface Alert {
  id: string;
  farmer_id: string | null;
  type: "hail" | "heavy_rain" | "scheme" | "price";
  title: string;
  detail: string;
  source_url: string;
  evidence: Evidence[];
  claim_id: string | null;
  created_at: string;
}
export interface Ticket {
  id: string;
  farmer_id: string | null;
  intent: "sell" | "subsidy" | "claim" | "advisory" | "unknown";
  query: string;
  reason: string;
  status: "open" | "closed";
  created_at: string;
}
export interface RunRecord {
  id: string;
  kind: "search" | "fetch" | "agent" | "monitor";
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  target: string;
  streaming_url: string | null;
  video_url: string | null;
  steps: number | null;
  mode: "live" | "replay";
  created_at: string;
  updated_at: string;
}
export interface Health {
  status: "ok";
  version: string;
  tinyfish_mode: "live" | "replay";
  db_backend: "sqlite" | "supabase";
  demo_state: string;
  demo_district: string;
  tinyfish_configured?: boolean;
  whatsapp_configured?: boolean;
  speech_to_text_configured?: boolean;
  public_webhook_ready?: boolean;
  watch_mode_ready?: boolean;
}

/** The backend could not be reached at all (as opposed to answering with an error). */
export class Unreachable extends Error {}

const as = <T>(v: unknown) => v as T;

async function request<T>(path: string, init?: RequestInit, timeoutMs = 20000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...init, signal: ctl.signal });
  } catch {
    throw new Unreachable(`Cannot reach the backend at ${API_BASE || "this origin"}`);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    // A static host (Vercel) answers 404/405 for backend paths when no backend is configured.
    if (!API_BASE && (res.status === 404 || res.status === 405) && !path.startsWith("/files/")) {
      throw new Unreachable("No backend configured (set VITE_API_BASE)");
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function withMock<T>(live: () => Promise<T>, mock: () => T): Promise<T> {
  try {
    return await live();
  } catch (e) {
    if (e instanceof Unreachable) return mock();
    throw e;
  }
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const fileUrl = (path: string) => (path.startsWith("http") ? path : `${API_BASE}${path}`);

export async function getHealth(): Promise<{ mode: Mode; health: Health | null }> {
  try {
    const health = await request<Health>("/health", undefined, 4000);
    return { mode: health.tinyfish_mode, health };
  } catch (e) {
    if (e instanceof Unreachable) return { mode: "mock", health: null };
    throw e;
  }
}

export const getFarmers = () => withMock(() => request<Farmer[]>("/api/farmers"), () => as<Farmer[]>(farmersMock));

export const chat = (text: string, farmerId?: string) =>
  withMock(
    () => request<GatedResponse>("/api/chat", json("POST", { text, farmer_id: farmerId }), 60000),
    () => as<GatedResponse>(/(ml|dawai|spray|dose)/i.test(text) ? chatDoseMock : chatMenuMock),
  );

export const sell = (crop: string, quantityQtl: number, farmerId?: string) =>
  withMock(
    () => request<GatedResponse>("/api/sell", json("POST", { crop, quantity_qtl: quantityQtl, farmer_id: farmerId }), 120000),
    () => as<GatedResponse>(sellMock),
  );

export const getSchemes = (farmerId?: string) =>
  withMock(
    () => request<SchemesResponse>(`/api/schemes${farmerId ? `?farmer_id=${encodeURIComponent(farmerId)}` : ""}`),
    () => as<SchemesResponse>(schemesMock),
  );

/** These operations must reach the real backend; a local sample must never be marked as reviewed. */
export const getSchemeReviewQueue = () => request<SchemeCatalogItem[]>("/api/schemes/review-queue");

export const reviewScheme = (schemeId: string, reviewer: string) =>
  request<SchemeCatalogItem>(`/api/schemes/${encodeURIComponent(schemeId)}/review`, json("POST", {
    reviewer,
    sources_read: true,
  }));

export interface SchemeDiscoveryResult {
  mode: Mode;
  count: number;
  created: Array<{ id: string; name: string; sources: SchemeSourceRecord[] }>;
  note: string;
}

/** Explicit operator action; it never uses offline mocks because discovery must be honestly labeled. */
export const discoverSchemes = () =>
  request<SchemeDiscoveryResult>("/api/schemes/discover", json("POST", {}), 120000);

export interface ClaimInput {
  farmerId: string;
  crop: string;
  event: string;
  eventDate: string;
  files: File[];
  deviceLocation: { lat: number; lon: number } | null;
}

export const submitClaim = (c: ClaimInput) =>
  withMock(
    () => {
      const form = new FormData();
      form.set("farmer_id", c.farmerId);
      form.set("crop", c.crop);
      form.set("event", c.event);
      form.set("event_date", c.eventDate);
      if (c.deviceLocation) {
        form.set("device_lat", String(c.deviceLocation.lat));
        form.set("device_lon", String(c.deviceLocation.lon));
      }
      c.files.forEach((f) => form.append("files", f, f.name));
      return request<ClaimResponse>("/api/claim/photos", { method: "POST", body: form }, 120000);
    },
    () => as<ClaimResponse>(claimMock),
  );

// The mock ledger is mutable so a confirm in sample mode visibly moves the Rs Unlocked number.
let mockLedger: LedgerResponse = structuredClone(as<LedgerResponse>(ledgerMock));

export const getLedger = (farmerId?: string) =>
  withMock(
    () => request<LedgerResponse>(`/api/ledger${farmerId ? `?farmer_id=${encodeURIComponent(farmerId)}` : ""}`),
    () => structuredClone(mockLedger),
  );

export const confirmEntry = (id: string) =>
  withMock(
    () => request<LedgerEntry>(`/api/ledger/${encodeURIComponent(id)}/confirm`, { method: "POST" }),
    () => {
      const entries = mockLedger.entries.map((e) => (e.id === id ? { ...e, confirmed: true } : e));
      const sum = (f: (e: LedgerEntry) => boolean) => entries.filter(f).reduce((n, e) => n + e.amount_rs, 0);
      mockLedger = { ...mockLedger, entries, total_rs: sum((e) => e.confirmed), projected_rs: sum((e) => !e.confirmed) };
      return entries.find((e) => e.id === id) as LedgerEntry;
    },
  );

export const getAlerts = (farmerId?: string) =>
  withMock(
    () => request<Alert[]>(`/api/alerts${farmerId ? `?farmer_id=${encodeURIComponent(farmerId)}` : ""}`),
    () => as<Alert[]>(alertsMock),
  );

/** Demo trigger: replays the recorded hail warning through Watch Mode. 409 means it was already raised. */
export const replayHail = () =>
  withMock(
    () => request<Alert>("/demo/replay-monitor", json("POST", { fixture_name: "hail" })),
    () => as<Alert[]>(alertsMock)[0],
  );

export const getRuns = () => withMock(() => request<RunRecord[]>("/api/runs?limit=10"), () => as<RunRecord[]>(runsMock));

/** No invented tickets in offline sample mode; an empty list is more honest than synthetic escalations. */
export const getTickets = () => withMock(() => request<Ticket[]>("/api/tickets?status=open"), () => []);

/**
 * The agent run behind the question being asked right now: the newest agent run started since `sinceMs`.
 * The web app polls /api/runs while a question is in flight, because the answer only arrives at the end
 * but the live browser view (streaming_url) exists from the first seconds of the run.
 */
export function pickRun(runs: RunRecord[], sinceMs: number): RunRecord | null {
  const mine = runs
    .filter((r) => r.kind === "agent" && Date.parse(r.created_at) >= sinceMs - 2000)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return mine[0] ?? null;
}
