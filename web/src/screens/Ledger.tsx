import { useState } from "react";
import { confirmEntry, type LedgerResponse } from "../api";
import { Button, Card, Chip } from "../components/ui";
import { rupees, shortDate } from "../format";
import { useI18n } from "../i18n";

export function Ledger({ ledger, onChange }: { ledger: LedgerResponse | null; onChange: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState<string | null>(null);

  const confirm = async (id: string) => {
    setBusy(id);
    try {
      await confirmEntry(id);
      onChange();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="text-xs font-medium text-neutral-600 dark:text-neutral-400">{t("ledgerTitle")}</div>
        <div className="text-5xl font-extrabold tracking-tight text-green-700 dark:text-green-500" data-testid="unlocked">
          {rupees(ledger?.total_rs ?? 0)}
        </div>
        <div className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">{t("confirmedOnly")}</div>
        <div className="mt-3 rounded-xl bg-amber-50 p-3 dark:bg-amber-900/30">
          <div className="text-lg font-bold">{rupees(ledger?.projected_rs ?? 0)}</div>
          <div className="text-xs text-neutral-700 dark:text-neutral-300">{t("projected")}</div>
        </div>
      </Card>

      <Card title={t("ledgerFormula")}>
        {!ledger?.entries.length ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">{t("ledgerEmpty")}</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {ledger.entries.map((e) => (
              <li key={e.id} className="py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Chip>{e.kind}</Chip>
                    <span className="text-xs text-neutral-500">{shortDate(e.created_at)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{rupees(e.amount_rs)}</span>
                    {e.confirmed ? (
                      <Chip tone="good">{t("confirmed")}</Chip>
                    ) : (
                      <Button variant="ghost" className="min-h-9 px-3 py-1 text-xs" disabled={busy === e.id} onClick={() => confirm(e.id)}>
                        {t("confirm")}
                      </Button>
                    )}
                  </div>
                </div>
                <p className="mt-1 break-words text-xs text-neutral-600 dark:text-neutral-400">{e.formula}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
