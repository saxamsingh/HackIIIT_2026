import { useCallback, useEffect, useState } from "react";
import {
  confirmEntry,
  discoverSchemes,
  getAlerts,
  getFarmers,
  getHealth,
  getLedger,
  getRuns,
  getSchemeReviewQueue,
  reviewScheme,
  getTickets,
  type Alert,
  type Farmer,
  type LedgerResponse,
  type Health,
  type Mode,
  type RunRecord,
  type SchemeCatalogItem,
  type Ticket,
} from "../api";
import { Button, Card, Chip, ErrorNote } from "../components/ui";
import { rupees, safeHref, shortDate } from "../format";

interface Snapshot {
  farmers: Farmer[];
  alerts: Alert[];
  ledger: LedgerResponse;
  runs: RunRecord[];
  tickets: Ticket[];
  reviewQueue: SchemeCatalogItem[];
  health: Health | null;
  mode: Mode;
}

const empty: Snapshot = { farmers: [], alerts: [], ledger: { farmer_id: null, total_rs: 0, projected_rs: 0, entries: [] }, runs: [], tickets: [], reviewQueue: [], health: null, mode: "mock" };

export function OperatorDashboard({ onExit }: { onExit: () => void }) {
  const [data, setData] = useState<Snapshot>(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState(() => {
    try { return localStorage.getItem("khetkaaj.reviewer") ?? ""; } catch { return ""; }
  });
  const [reviewAck, setReviewAck] = useState<Record<string, boolean>>({});
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [reviewQueueError, setReviewQueueError] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryMessage, setDiscoveryMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [farmers, alerts, ledger, runs, tickets, healthResult] = await Promise.all([
        getFarmers(), getAlerts(), getLedger(), getRuns(), getTickets(), getHealth(),
      ]);
      let reviewQueue: SchemeCatalogItem[] = [];
      try {
        reviewQueue = await getSchemeReviewQueue();
        setReviewQueueError(null);
      } catch (queueError) {
        setReviewQueueError(queueError instanceof Error ? queueError.message : String(queueError));
      }
      setData({ farmers, alerts, ledger, runs, tickets, reviewQueue, health: healthResult.health, mode: healthResult.mode });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const approveLedger = async (id: string) => {
    setConfirming(id);
    try {
      await confirmEntry(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirming(null);
    }
  };

  const discoverSchemeNotices = async () => {
    setDiscovering(true);
    setDiscoveryMessage(null);
    try {
      const result = await discoverSchemes();
      const dataLabel = result.mode === "replay" ? "Replay fixtures" : "Live provider";
      setDiscoveryMessage(`${dataLabel}: ${result.count} new candidate(s). ${result.note}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDiscovering(false);
    }
  };

  const submitSchemeReview = async (scheme: SchemeCatalogItem) => {
    if (!reviewer.trim() || reviewer.trim().length < 2 || !reviewAck[scheme.id] || !scheme.sources.length) return;
    setReviewing(scheme.id);
    setReviewMessage(null);
    try {
      await reviewScheme(scheme.id, reviewer.trim());
      try { localStorage.setItem("khetkaaj.reviewer", reviewer.trim()); } catch { /* private browsing */ }
      setReviewAck((current) => ({ ...current, [scheme.id]: false }));
      setReviewMessage(`${scheme.name} is now visible in the farmer's scheme results. Verify the criteria and dates before advising a farmer.`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewing(null);
    }
  };

  const farmerName = (id: string | null) => data.farmers.find((f) => f.id === id)?.name ?? "Unlinked / unknown farmer";
  const pending = data.ledger.entries.filter((entry) => !entry.confirmed);
  const openTickets = data.tickets.filter((ticket) => ticket.status === "open");

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-green-700 dark:text-green-500">CSC / FPO</p>
          <h2 className="text-xl font-bold">Operator dashboard</h2>
          <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">Review queue and activity from the connected backend.</p>
        </div>
        <Button variant="ghost" onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button>
      </div>

      {error && <ErrorNote message={error} onRetry={() => void refresh()} />}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Card>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">Farmers in demo registry</p>
          <p className="mt-1 text-2xl font-bold">{data.farmers.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">Open escalations</p>
          <p className="mt-1 text-2xl font-bold">{openTickets.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">Active / recent alerts</p>
          <p className="mt-1 text-2xl font-bold">{data.alerts.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">₹ unlocked (confirmed)</p>
          <p className="mt-1 text-2xl font-bold text-green-700 dark:text-green-500">{rupees(data.ledger.total_rs)}</p>
          <p className="text-xs text-neutral-500">{rupees(data.ledger.projected_rs)} pending confirmation</p>
        </Card>
      </div>

      <Card title="Integration readiness">
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">Configuration checks only. A green “configured” state does not prove that a real provider request has succeeded.</p>
        <ul className="divide-y divide-stone-200 dark:divide-white/10">
          {[
            { label: "Market / portal browsing (TinyFish)", ready: data.health?.tinyfish_configured === true, detail: data.health?.tinyfish_configured ? "Live mode + API key present; live smoke test still required." : data.mode === "replay" ? "Replay fixtures are active; not live market data." : "Configure TINYFISH_MODE=live and TINYFISH_API_KEY." },
            { label: "WhatsApp messaging (Twilio)", ready: data.health?.whatsapp_configured === true, detail: data.health?.whatsapp_configured ? "Credentials are present; send a real Sandbox test message." : "Set Account SID, Auth Token and WhatsApp sender in .env." },
            { label: "Voice note transcription (Bhashini)", ready: data.health?.speech_to_text_configured === true, detail: data.health?.speech_to_text_configured ? "Credentials are present; send a real Hindi/English voice note to verify." : "Voice notes cannot be transcribed live until Bhashini credentials are configured." },
            { label: "Automated Watch Mode", ready: data.health?.watch_mode_ready === true, detail: data.health?.watch_mode_ready ? "Monitor prerequisites are present; create monitors and verify an inbound webhook." : "Requires live TinyFish, public HTTPS URL, webhook token and monitor creation." },
            { label: "Database", ready: Boolean(data.health), detail: data.health ? `${data.health.db_backend.toUpperCase()} · ${data.mode === "mock" ? "backend unreachable" : "backend responds"}` : "Backend health was not available." },
          ].map((item) => (
            <li key={item.label} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold">{item.label}</p>
                <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">{item.detail}</p>
              </div>
              <Chip tone={item.ready ? "good" : "warn"}>{item.ready ? "Configured" : "Not ready"}</Chip>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-neutral-500">See README.md and docs/TWILIO_SANDBOX.md for provider setup and live smoke tests. No credentials are embedded in the app.</p>
      </Card>

      <Card title="Scheme discovery & review">
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">Search for new scheme notices through the configured provider. Discovery creates unreviewed candidates only; it never publishes a scheme or claims eligibility.</p>
        <Button className="w-full" onClick={() => void discoverSchemeNotices()} disabled={discovering || loading}>
          {discovering ? "Searching for notices…" : "Discover new scheme notices"}
        </Button>
        {discoveryMessage && <p role="status" className="mt-3 rounded-xl bg-stone-100 p-3 text-sm dark:bg-white/5">{discoveryMessage}</p>}
      </Card>

      <Card title="Scheme review queue">
        {reviewQueueError && <ErrorNote message={`Scheme review queue requires a reachable, updated backend: ${reviewQueueError}`} />}
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">New or unreviewed scheme records stay hidden from farmers until a person checks the cited sources and acknowledges this review. This is a local demo workflow, not an authenticated approval system.</p>
        <div className="mb-3">
          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">Reviewer name
            <input className="mt-1 w-full min-h-11 rounded-xl border border-stone-300 bg-stone-50 px-3 py-2 text-base dark:border-white/10 dark:bg-neutral-950" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" maxLength={100} />
          </label>
        </div>
        {reviewMessage && <p role="status" className="mb-3 rounded-xl bg-green-50 p-3 text-sm text-green-900 dark:bg-green-900/30 dark:text-green-100">{reviewMessage}</p>}
        {data.reviewQueue.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No unreviewed candidates. Reviewed schemes can be found on the farmer Schemes screen.</p>
        ) : (
          <ul className="space-y-3">
            {data.reviewQueue.map((scheme) => (
              <li key={scheme.id} className="rounded-xl border border-stone-200 p-3 dark:border-white/10">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">{scheme.name}</h3>
                  <Chip tone="warn">Needs human review</Chip>
                </div>
                <p className="mt-1 text-sm">{scheme.benefit}</p>
                {scheme.discovered && <Chip tone="warn">Auto-discovered candidate</Chip>}
                {scheme.notes && <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">Review notes: {scheme.notes}</p>}
                {scheme.discovered && Object.keys(scheme.eligibility ?? {}).length === 0 && <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-100">This record has no structured eligibility rules yet. Edit its YAML catalog entry, verify the official rules and benefit, then return to review it.</p>}
                <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">Required profile facts: {scheme.requires_facts.join(", ") || "No additional facts recorded"} · Documents: {scheme.requires_documents.join(", ") || "None listed"}</p>
                <div className="mt-3 space-y-1 text-sm">
                  {scheme.sources.map((source) => (
                    <p key={source.url} className="break-all">
                      <a className="font-medium text-green-800 underline dark:text-green-400" href={safeHref(source.url)} target="_blank" rel="noreferrer noopener">{source.title || source.url}</a>
                      {source.retrieved && <span className="ml-1 text-xs text-neutral-500">(listed as retrieved {source.retrieved})</span>}
                    </p>
                  ))}
                  {scheme.sources.length === 0 && <p className="text-xs text-red-700 dark:text-red-300">No sources attached: this record cannot be reviewed safely.</p>}
                  {safeHref(scheme.apply_url) && <p className="text-xs"><a className="underline" href={safeHref(scheme.apply_url)} target="_blank" rel="noreferrer noopener">Application portal</a> · {scheme.url_verified ? "portal URL marked verified in the catalog" : "application URL still needs verification"}</p>}
                </div>
                <label className="mt-3 flex items-start gap-2 text-xs text-neutral-700 dark:text-neutral-300">
                  <input type="checkbox" className="mt-0.5" checked={Boolean(reviewAck[scheme.id])} onChange={(e) => setReviewAck((current) => ({ ...current, [scheme.id]: e.target.checked }))} />
                  I opened and reviewed the source(s), eligibility rules, benefit, and any deadline before publishing this record.
                </label>
                <Button className="mt-3 w-full" disabled={reviewing !== null || reviewer.trim().length < 2 || !reviewAck[scheme.id] || scheme.sources.length === 0 || Boolean(scheme.discovered && Object.keys(scheme.eligibility ?? {}).length === 0)} onClick={() => void submitSchemeReview(scheme)}>
                  {reviewing === scheme.id ? "Publishing…" : "Mark reviewed and publish"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Human review queue">
        {openTickets.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No open escalations. Safety-gated questions will appear here.</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {openTickets.map((ticket) => (
              <li key={ticket.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone="warn">{ticket.intent}</Chip>
                  <Chip>{ticket.id}</Chip>
                  <span className="text-xs text-neutral-500">{shortDate(ticket.created_at)}</span>
                </div>
                <p className="mt-2 text-sm font-semibold">{farmerName(ticket.farmer_id)}</p>
                <p className="mt-1 whitespace-pre-line break-words text-sm">{ticket.query}</p>
                <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">Reason: {ticket.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Pending ledger confirmations">
        {pending.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No proposed entries are waiting for confirmation.</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {pending.map((entry) => (
              <li key={entry.id} className="py-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">{farmerName(entry.farmer_id)}</p>
                    <p className="text-xs text-neutral-500">{entry.kind} · {shortDate(entry.created_at)}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-bold">{rupees(entry.amount_rs)}</p>
                    <Button className="mt-1 min-h-9 px-3 py-1 text-xs" variant="ghost" disabled={confirming === entry.id} onClick={() => void approveLedger(entry.id)}>
                      {confirming === entry.id ? "Saving…" : "Confirm entry"}
                    </Button>
                  </div>
                </div>
                <p className="mt-1 break-words text-xs text-neutral-600 dark:text-neutral-400">{entry.formula}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Recent alerts">
        {data.alerts.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No alerts available.</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {data.alerts.slice(0, 8).map((alert) => (
              <li key={alert.id} className="py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold">{alert.title}</p>
                  <Chip tone={alert.type === "hail" || alert.type === "heavy_rain" ? "warn" : "neutral"}>{alert.type}</Chip>
                </div>
                <p className="mt-1 break-words text-sm">{alert.detail}</p>
                <p className="mt-1 text-xs text-neutral-500">{farmerName(alert.farmer_id)} · {shortDate(alert.created_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Agent execution history">
        {data.runs.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No execution records yet.</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {data.runs.slice(0, 10).map((run) => (
              <li key={run.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone={run.status === "COMPLETED" ? "good" : run.status === "FAILED" ? "bad" : "neutral"}>{run.status}</Chip>
                  <Chip tone={run.mode === "replay" ? "warn" : "good"}>{run.mode}</Chip>
                  <span className="text-xs text-neutral-500">{run.kind} · {shortDate(run.updated_at)}</span>
                </div>
                <p className="mt-1 break-words text-sm">{run.target}</p>
                <p className="mt-1 font-mono text-xs text-neutral-500">{run.id}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Farmer directory">
        {data.farmers.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">No farmer records available.</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {data.farmers.map((farmer) => (
              <li key={farmer.id} className="py-3">
                <p className="text-sm font-semibold">{farmer.name}</p>
                <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">{farmer.district}, {farmer.state} · {farmer.land_acres} acres</p>
                <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">Crops: {farmer.crops.join(", ") || "Not provided"} · Language: {farmer.language}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-xs text-neutral-500">Hackathon MVP: replay/demo data is labeled separately from live provider data. This dashboard is not an authenticated production operator console.</p>
      <Button variant="ghost" className="w-full" onClick={onExit}>Return to farmer app</Button>
    </div>
  );
}
