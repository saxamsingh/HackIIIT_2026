import { useCallback, useState } from "react";
import { sell, type GatedResponse, type SellData } from "../api";
import { ConfirmBar } from "../components/ConfirmBar";
import { LiveRunViewer } from "../components/LiveRunViewer";
import { Button, Card, Chip, ErrorNote, Escalation, Field, SourceChip, SourceList, inputClass } from "../components/ui";
import { rupees } from "../format";
import { useWatchedCall } from "../hooks/useWatchedCall";
import { useI18n, type Key } from "../i18n";

const CROPS: { value: string; label: Key }[] = [
  { value: "wheat", label: "wheat" },
  { value: "rice", label: "rice" },
  { value: "mustard", label: "mustard" },
  { value: "chickpea", label: "chickpea" },
];

export function Sell({ farmerId, onLedgerChange }: { farmerId: string | undefined; onLedgerChange: () => void }) {
  const { t } = useI18n();
  const [crop, setCrop] = useState("wheat");
  const [qty, setQty] = useState("20");
  const quantity = Number(qty);
  const call = useCallback(() => sell(crop, quantity, farmerId), [crop, quantity, farmerId]);
  const watched = useWatchedCall<GatedResponse>(call);
  const r = watched.result;
  const d = r?.status === "answered" ? (r.data as SellData) : null;

  return (
    <div className="space-y-4">
      <Card>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            watched.start();
          }}
        >
          <Field label={t("crop")}>
            <select className={inputClass} value={crop} onChange={(e) => setCrop(e.target.value)}>
              {CROPS.map((c) => (
                <option key={c.value} value={c.value}>
                  {t(c.label)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("quantity")}>
            <input
              className={inputClass}
              type="number"
              inputMode="decimal"
              min="1"
              step="any"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              required
            />
          </Field>
          <Button type="submit" className="w-full" disabled={watched.running || !(quantity > 0)}>
            {watched.running ? t("running") : t("findMandi")}
          </Button>
        </form>
      </Card>

      <LiveRunViewer run={watched.agentRun} running={watched.running} rung={d?.rung} />
      {watched.error && <ErrorNote message={watched.error} onRetry={watched.start} />}
      {r && r.status !== "answered" && r.status !== "menu" && <Escalation response={r} />}

      {d && r && (
        <>
          <Card>
            {d.data_mode === "replay" && (
              <p className="mb-3 rounded-xl bg-amber-50 p-2 text-xs text-amber-950 dark:bg-amber-900/30 dark:text-amber-100">
                {t("replayData")}
              </p>
            )}
            <div className="text-xs font-medium text-neutral-600 dark:text-neutral-400">{t("bestNet")}</div>
            <div className="text-3xl font-bold text-green-700 dark:text-green-500">
              {rupees(d.best.net_price)}
              <span className="ml-2 text-sm font-normal text-neutral-600 dark:text-neutral-400">{t("perQtl")}</span>
            </div>
            <div className="mt-1 text-base font-semibold">{d.best.mandi}</div>
            {d.gain_rs > 0 && (
              <div className="mt-3 rounded-xl bg-green-50 p-3 dark:bg-green-900/30">
                <div className="text-xl font-bold">+{rupees(d.gain_rs)}</div>
                <div className="text-xs text-neutral-700 dark:text-neutral-300">
                  {t("extraEarn")} ({d.nearest.mandi}) · {d.quantity_qtl} qtl
                </div>
              </div>
            )}
            <p className="mt-3 text-sm">
              {d.msp.price_rs_per_qtl ? (
                <>
                  {t("mspLine")} {rupees(d.msp.price_rs_per_qtl)} ({t("mspSeason")} {d.msp.marketing_season}):{" "}
                  <Chip tone={d.msp.below_msp ? "bad" : "good"}>
                    {d.msp.below_msp ? t("mspBelow") : t("mspAbove")}{" "}
                    {rupees(Math.abs(d.msp.difference_rs ?? 0))}
                  </Chip>
                </>
              ) : (
                <span className="text-neutral-600 dark:text-neutral-400">{t("noMsp")}</span>
              )}
            </p>
            <p className="mt-2 break-words text-xs text-neutral-600 dark:text-neutral-400">{d.formula}</p>
            {d.ledger_entry_id && <ConfirmBar entryId={d.ledger_entry_id} onConfirmed={onLedgerChange} />}
          </Card>

          <Card title={t("ranked")}>
            <ol className="divide-y divide-stone-200 dark:divide-white/10">
              {d.options.map((o, i) => (
                <li key={o.mandi} className="flex items-start justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 font-medium">
                      <span className="text-neutral-500">{i + 1}.</span>
                      {o.mandi}
                      {o.mandi === d.nearest.mandi && <Chip>{t("nearest")}</Chip>}
                    </div>
                    <div className="text-xs text-neutral-600 dark:text-neutral-400">
                      {o.distance_km} {t("km")}
                      {o.distance_assumed ? "*" : ""} · {t("transport")} {rupees(o.transport_cost)}
                    </div>
                    {r.evidence[i] && (
                      <div className="mt-1 text-xs">
                        {t("source")}: <SourceChip ev={r.evidence[i]} />
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="font-semibold">{rupees(o.net_price)}</div>
                    <div className="text-xs text-neutral-500 line-through">{rupees(o.modal_price)}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          {(d.warnings.length > 0 || d.assumptions.length > 0) && (
            <Card>
              {d.warnings.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold">{t("warnings")}</h3>
                  <ul className="mb-3 list-inside list-disc text-xs">{d.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                </>
              )}
              {d.assumptions.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold">{t("assumptions")}</h3>
                  <ul className="list-inside list-disc text-xs text-neutral-600 dark:text-neutral-400">
                    {d.assumptions.map((a) => <li key={a}>{a}</li>)}
                  </ul>
                </>
              )}
              <SourceList sources={r.evidence.slice(-1).filter((e) => e.kind === "knowledge")} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
