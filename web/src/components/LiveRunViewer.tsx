import type { RunRecord } from "../api";
import { frameableUrl, safeHref } from "../format";
import { useI18n } from "../i18n";
import { Card, Chip } from "./ui";

/**
 * Shows the browser agent at work. While a question is being answered, the newest agent run is polled and its
 * TinyFish live view (`streaming_url`) is framed here; a recording (`video_url`) is the fallback; the step
 * count and status are always shown. When the answer needed no browser run (the page could be read directly)
 * `rung` is "fetch" and the card says so instead of staying empty.
 */
export function LiveRunViewer({
  run,
  running,
  rung,
}: {
  run: RunRecord | null;
  running: boolean;
  rung?: "fetch" | "agent";
}) {
  const { t } = useI18n();
  const frame = frameableUrl(run?.streaming_url);
  const video = safeHref(run?.video_url ?? undefined);

  if (!run && !running && !rung) return null;
  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-base font-semibold">{frame ? t("liveView") : t("steps")}</h2>
        {running && (
          <span className="flex items-center gap-1.5 text-xs text-green-700 dark:text-green-500" role="status">
            <span className="h-2 w-2 animate-pulse rounded-full bg-green-600" />
            {t("running")}
          </span>
        )}
      </div>
      {frame ? (
        <iframe
          title={t("liveView")}
          src={frame}
          className="mb-3 aspect-[16/10] w-full rounded-xl border border-stone-300 dark:border-white/10"
          sandbox="allow-scripts allow-same-origin"
          referrerPolicy="no-referrer"
        />
      ) : video ? (
        <video className="mb-3 w-full rounded-xl" src={video} controls playsInline aria-label={t("recording")} />
      ) : null}
      {run && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Chip tone={run.status === "FAILED" ? "bad" : run.status === "COMPLETED" ? "good" : "neutral"}>{run.status}</Chip>
          {run.steps != null && (
            <span>
              {run.steps} {t("steps").toLowerCase()}
            </span>
          )}
          <Chip tone={run.mode === "live" ? "good" : "warn"}>{run.mode}</Chip>
        </div>
      )}
      {!run && running && <p className="text-sm text-neutral-500">{t("waiting")}</p>}
      {!running && rung && (
        <p className="mt-2 text-sm text-neutral-700 dark:text-neutral-300">
          {rung === "fetch" ? t("answeredFetch") : t("answeredAgent")}
        </p>
      )}
    </Card>
  );
}
