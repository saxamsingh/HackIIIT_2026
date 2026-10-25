import { useState } from "react";
import { chat, fileUrl, replayHail, type Alert, type GatedResponse, type LedgerResponse } from "../api";
import type { Tab } from "../components/TabBar";
import { Button, Card, Chip, ErrorNote, Escalation, SourceChip, inputClass } from "../components/ui";
import { rupees, shortDate } from "../format";
import { useI18n } from "../i18n";

interface Props {
  farmerId: string | undefined;
  ledger: LedgerResponse | null;
  alerts: Alert[];
  onAlertsChange: () => void;
  onLedgerChange: () => void;
  go: (t: Tab) => void;
}

export function Home({ farmerId, ledger, alerts, onAlertsChange, onLedgerChange, go }: Props) {
  const { t, lang } = useI18n();
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState<GatedResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const ask = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await chat(text, farmerId));
      onLedgerChange(); // a sell answer records a projected value
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const replay = async () => {
    setNote(null);
    setError(null);
    try {
      await replayHail();
      onAlertsChange();
    } catch (e) {
      // 409 means the same warning was already raised, which is not a failure.
      const message = e instanceof Error ? e.message : String(e);
      if (/already|nothing changed/i.test(message)) setNote(t("alreadyRaised"));
      else setError(message);
    }
  };

  return (
    <div className="space-y-4">
      <button
        onClick={() => go("ledger")}
        className="block w-full rounded-2xl bg-green-700 p-4 text-left text-white shadow-sm active:bg-green-800"
      >
        <div className="text-xs font-medium opacity-90">{t("unlocked")}</div>
        <div className="text-4xl font-extrabold">{rupees(ledger?.total_rs ?? 0)}</div>
        <div className="mt-1 text-xs opacity-90">
          {rupees(ledger?.projected_rs ?? 0)} · {t("projected")}
        </div>
      </button>

      <div className="grid grid-cols-3 gap-2">
        {([
          ["sell", "quickSell"],
          ["schemes", "quickSchemes"],
          ["claim", "quickClaim"],
        ] as const).map(([tab, label]) => (
          <button
            key={tab}
            onClick={() => go(tab)}
            className="min-h-14 rounded-xl border border-stone-200 bg-white p-2 text-sm font-semibold active:bg-green-50 dark:border-white/10 dark:bg-neutral-900"
          >
            {t(label)}
          </button>
        ))}
      </div>

      <Card title={t("askTitle")}>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <input
            className={inputClass}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("askPlaceholder")}
            lang={lang}
            aria-label={t("askTitle")}
          />
          <Button type="submit" disabled={busy}>
            {busy ? t("asking") : t("ask")}
          </Button>
        </form>
        {answer && answer.status === "escalated" && (
          <div className="mt-3">
            <Escalation response={answer} />
          </div>
        )}
        {answer && answer.status !== "escalated" && (
          <p className="mt-3 whitespace-pre-line rounded-xl bg-green-50 p-3 text-sm dark:bg-green-900/30">{answer.reply}</p>
        )}
        {error && (
          <div className="mt-3">
            <ErrorNote message={error} />
          </div>
        )}
      </Card>

      <Card title={t("homeAlerts")}>
        {alerts.length === 0 ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">{t("homeNoAlerts")}</p>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-white/10">
            {alerts.slice(0, 5).map((a) => (
              <li key={a.id} className="py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold">{a.title}</span>
                  <Chip tone={a.type === "hail" || a.type === "heavy_rain" ? "warn" : "good"}>{shortDate(a.created_at)}</Chip>
                </div>
                <p className="mt-1 break-words text-sm">{a.detail}</p>
                {a.evidence[0] && (
                  <div className="mt-1">
                    <SourceChip ev={a.evidence[0]} />
                  </div>
                )}
                {a.claim_id && (
                  <a
                    className="mt-2 inline-flex min-h-11 items-center rounded-xl bg-green-700 px-4 text-sm font-semibold text-white"
                    href={fileUrl(`/files/dossier-${a.claim_id}.pdf`)}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {t("openDossier")}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        {note && <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">{note}</p>}
        <div className="mt-3 border-t border-stone-200 pt-3 dark:border-white/10">
          <Button variant="ghost" onClick={replay}>
            {t("simulateHail")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
