import type { Mode } from "../api";
import { useI18n } from "../i18n";

const style: Record<Mode, string> = {
  live: "bg-green-100 text-green-900 dark:bg-green-900 dark:text-green-100",
  replay: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
  mock: "bg-neutral-200 text-neutral-800 dark:bg-white/15 dark:text-neutral-200",
};

export function ModeBadge({ mode }: { mode: Mode }) {
  const { t } = useI18n();
  const label = { live: t("modeLive"), replay: t("modeReplay"), mock: t("modeMock") }[mode];
  const hint = { live: t("modeLiveHint"), replay: t("modeReplayHint"), mock: t("modeMockHint") }[mode];
  return (
    <span title={hint} aria-label={`${label}: ${hint}`} className={`rounded-full px-2.5 py-1 text-xs font-semibold ${style[mode]}`}>
      {label}
    </span>
  );
}
