import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Evidence, GatedResponse } from "../api";
import { host, safeHref } from "../format";
import { reasonLabel, useI18n } from "../i18n";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-2xl border border-stone-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-neutral-900 ${className}`}
    >
      {title && <h2 className="mb-2 text-base font-semibold">{title}</h2>}
      {children}
    </section>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const base =
    "min-h-11 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-default disabled:opacity-50";
  const style =
    variant === "primary"
      ? "bg-green-700 text-white active:bg-green-800"
      : "border border-green-700 text-green-700 active:bg-green-50 dark:border-green-500 dark:text-green-500 dark:active:bg-white/5";
  return <button className={`${base} ${style} ${className}`} {...rest} />;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
      {label}
      <div className="mt-1 text-base font-normal text-neutral-900 dark:text-neutral-100">{children}</div>
    </label>
  );
}

export const inputClass =
  "w-full min-h-11 rounded-xl border border-stone-300 bg-stone-50 px-3 py-2 text-base dark:border-white/10 dark:bg-neutral-950";

type Tone = "good" | "warn" | "neutral" | "bad";
export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    good: "bg-green-100 text-green-900 dark:bg-green-900/50 dark:text-green-100",
    warn: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
    bad: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200",
    neutral: "bg-neutral-100 text-neutral-700 dark:bg-white/10 dark:text-neutral-300",
  };
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

/** Where a fact came from. A replayed answer is shown as replay, never as live. */
export function SourceChip({ ev }: { ev: Evidence }) {
  const tone: Tone = ev.kind === "replay" ? "warn" : ev.assumed ? "warn" : "good";
  const href = safeHref(ev.source_url);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
      {href ? (
        <a className="break-all underline" href={href} target="_blank" rel="noreferrer noopener" title={ev.quote ?? undefined}>
          {host(ev.source_url)}
        </a>
      ) : (
        <span>{ev.source_url}</span>
      )}
      <Chip tone={tone}>{ev.kind}</Chip>
    </span>
  );
}

export function SourceList({ sources }: { sources: Evidence[] }) {
  const { t } = useI18n();
  const unique = sources.filter((s, i) => sources.findIndex((o) => o.source_url === s.source_url && o.kind === s.kind) === i);
  if (!unique.length) return null;
  return (
    <div className="mt-3 text-xs text-neutral-600 dark:text-neutral-400">
      <div className="mb-1 font-medium">{t("sources")}</div>
      <ul className="space-y-1">
        {unique.map((s) => (
          <li key={s.source_url + s.kind}>
            <SourceChip ev={s} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-900 dark:bg-red-900/30 dark:text-red-100">
      <div className="font-semibold">{t("error")}</div>
      <div className="mt-1 break-words">{message}</div>
      {onRetry && (
        <Button variant="ghost" className="mt-2" onClick={onRetry}>
          {t("retry")}
        </Button>
      )}
    </div>
  );
}

/** An answer the gate withheld. Shows the hand-off and why, and never any recommendation. */
export function Escalation({ response }: { response: Pick<GatedResponse, "reply" | "ticket_id" | "reasons"> }) {
  const { t } = useI18n();
  return (
    <div className="rounded-xl border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-900/30 dark:text-amber-100">
      <div className="font-semibold">{t("escalateTitle")}</div>
      <p className="mt-1">{t("escalateBody")}</p>
      <p className="mt-2 whitespace-pre-line text-xs opacity-90">{response.reply}</p>
      {response.reasons.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs opacity-80">
          {response.reasons.map((r) => (
            <li key={r}>{reasonLabel(t, r)}</li>
          ))}
        </ul>
      )}
      {response.ticket_id && (
        <p className="mt-2 text-xs">
          {t("ticket")}: <code>{response.ticket_id}</code>
        </p>
      )}
    </div>
  );
}
