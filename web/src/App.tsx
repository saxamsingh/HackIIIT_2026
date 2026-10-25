import { useCallback, useEffect, useState } from "react";
import {
  getAlerts,
  getFarmers,
  getHealth,
  getLedger,
  type Alert,
  type Farmer,
  type LedgerResponse,
  type Mode,
} from "./api";
import { ModeBadge } from "./components/ModeBadge";
import { TabBar, type Tab } from "./components/TabBar";
import { I18nProvider, useI18n } from "./i18n";
import { Claim } from "./screens/Claim";
import { Home } from "./screens/Home";
import { Ledger } from "./screens/Ledger";
import { OperatorDashboard } from "./screens/OperatorDashboard";
import { Schemes } from "./screens/Schemes";
import { Sell } from "./screens/Sell";

const FARMER_KEY = "khetkaaj.farmer";

function savedFarmer(): string | undefined {
  try {
    return localStorage.getItem(FARMER_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

function Shell() {
  const { t, toggle, lang } = useI18n();
  const [tab, setTab] = useState<Tab>("home");
  const [mode, setMode] = useState<Mode>("mock");
  const [farmers, setFarmers] = useState<Farmer[]>([]);
  const [farmerId, setFarmerId] = useState<string | undefined>(savedFarmer);
  const [ledger, setLedger] = useState<LedgerResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const refreshLedger = useCallback(() => void getLedger(farmerId).then(setLedger).catch(() => undefined), [farmerId]);
  const refreshAlerts = useCallback(() => void getAlerts(farmerId).then(setAlerts).catch(() => undefined), [farmerId]);

  useEffect(() => {
    void getHealth().then((h) => setMode(h.mode));
    void getFarmers()
      .then((list) => {
        setFarmers(list);
        setFarmerId((cur) => (cur && list.some((f) => f.id === cur) ? cur : list[0]?.id));
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshLedger();
    refreshAlerts();
  }, [refreshLedger, refreshAlerts]);

  const pickFarmer = (id: string) => {
    setFarmerId(id);
    try {
      localStorage.setItem(FARMER_KEY, id);
    } catch {
      /* ignore */
    }
  };

  // The ledger and alerts can change while another tab is open (a confirm, Watch Mode), so refresh on switch.
  const go = (next: Tab) => {
    setTab(next);
    if (next === "ledger" || next === "home") {
      refreshLedger();
      refreshAlerts();
    }
    window.scrollTo({ top: 0 });
  };

  return (
    <div lang={lang} className={`mx-auto min-h-screen pb-24 ${tab === "operator" ? "max-w-6xl" : "max-w-md"}`}>
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-stone-50/95 px-4 py-3 backdrop-blur dark:border-white/10 dark:bg-neutral-950/95">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h1 className="text-lg font-extrabold leading-tight text-green-700 dark:text-green-500">KhetKaaj</h1>
            <p className="truncate text-xs text-neutral-600 dark:text-neutral-400">{t("tagline")}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ModeBadge mode={mode} />
            <button
              onClick={() => go(tab === "operator" ? "home" : "operator")}
              className="min-h-9 rounded-full border border-stone-300 px-3 text-xs font-semibold text-neutral-700 dark:border-white/10 dark:text-neutral-200"
              aria-label={tab === "operator" ? "Return to farmer app" : "Open operator dashboard"}
            >
              {tab === "operator" ? "Farmer" : "Operator"}
            </button>
            <button
              onClick={toggle}
              className="min-h-9 rounded-full border border-green-700 px-3 text-xs font-semibold text-green-700 dark:border-green-500 dark:text-green-500"
            >
              {t("language")}
            </button>
          </div>
        </div>
        {tab !== "operator" && farmers.length > 0 && (
          <label className="mt-2 flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
            {t("farmer")}
            <select
              className="min-h-9 flex-1 rounded-lg border border-stone-300 bg-white px-2 text-sm text-neutral-900 dark:border-white/10 dark:bg-neutral-900 dark:text-neutral-100"
              value={farmerId}
              onChange={(e) => pickFarmer(e.target.value)}
            >
              {farmers.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name} · {f.district}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {mode === "replay" && (
        <div role="status" className="mx-4 mt-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100">
          <strong>Replay mode:</strong> web/market/weather lookups may use saved fixtures. These are not current live prices or alerts. Confirm important information with the linked official source.
        </div>
      )}
      {mode === "mock" && (
        <div role="status" className="mx-4 mt-3 rounded-xl border border-stone-300 bg-stone-100 px-3 py-2 text-xs text-neutral-800 dark:border-white/10 dark:bg-white/10 dark:text-neutral-200">
          <strong>Offline sample mode:</strong> the backend could not be reached. Some screens may show bundled examples, and changes may not persist. Start the backend to use the local database.
        </div>
      )}
      {mode === "live" && (
        <div role="status" className="mx-4 mt-3 rounded-xl border border-green-300 bg-green-50 px-3 py-2 text-xs text-green-950 dark:border-green-800 dark:bg-green-950/40 dark:text-green-100">
          <strong>Live mode configured:</strong> results can still be incomplete or blocked by source sites. Check the displayed evidence and dates before acting.
        </div>
      )}

      <main className="space-y-4 p-4">
        {tab === "operator" ? (
          <OperatorDashboard onExit={() => go("home")} />
        ) : (
          <>
            {tab === "home" && (
              <Home farmerId={farmerId} ledger={ledger} alerts={alerts} onAlertsChange={refreshAlerts}
                onLedgerChange={refreshLedger} go={go} />
            )}
            {tab === "sell" && <Sell farmerId={farmerId} onLedgerChange={refreshLedger} />}
            {tab === "schemes" && <Schemes farmerId={farmerId} />}
            {tab === "claim" && <Claim farmerId={farmerId} />}
            {tab === "ledger" && <Ledger ledger={ledger} onChange={refreshLedger} />}
          </>
        )}
      </main>

      {tab !== "operator" && <TabBar tab={tab} onChange={go} />}
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <Shell />
    </I18nProvider>
  );
}
