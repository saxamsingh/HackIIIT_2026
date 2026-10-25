import { useCallback, useEffect, useMemo, useState } from "react";
import { fileUrl, submitClaim, type ClaimResponse } from "../api";
import { LiveRunViewer } from "../components/LiveRunViewer";
import { Button, Card, Chip, ErrorNote, Field, SourceList, inputClass } from "../components/ui";
import { todayIso } from "../format";
import { useWatchedCall } from "../hooks/useWatchedCall";
import { useI18n } from "../i18n";

type Loc = { lat: number; lon: number } | null;

export function Claim({ farmerId }: { farmerId: string | undefined }) {
  const { t } = useI18n();
  const [crop, setCrop] = useState("wheat");
  const [event, setEvent] = useState("hail");
  const [date, setDate] = useState(todayIso());
  const [files, setFiles] = useState<File[]>([]);
  const [loc, setLoc] = useState<Loc>(null);
  const [locState, setLocState] = useState<"idle" | "busy" | "ok" | "denied">("idle");

  const call = useCallback(
    () => submitClaim({ farmerId: farmerId ?? "", crop, event, eventDate: date, files, deviceLocation: loc }),
    [farmerId, crop, event, date, files, loc],
  );
  const watched = useWatchedCall<ClaimResponse>(call);
  const r = watched.result;

  // Object URLs for the thumbnails; revoked when the selection changes.
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const getLocation = () => {
    if (!navigator.geolocation) return setLocState("denied");
    setLocState("busy");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLoc({ lat: p.coords.latitude, lon: p.coords.longitude });
        setLocState("ok");
      },
      () => setLocState("denied"),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

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
            <input className={inputClass} value={crop} onChange={(e) => setCrop(e.target.value)} required />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("event")}>
              <select className={inputClass} value={event} onChange={(e) => setEvent(e.target.value)}>
                <option value="hail">{t("hail")}</option>
                <option value="heavy_rain">{t("heavyRain")}</option>
                <option value="flood">{t("flood")}</option>
                <option value="other">{t("other")}</option>
              </select>
            </Field>
            <Field label={t("eventDate")}>
              <input className={inputClass} type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} required />
            </Field>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">{t("photos")}</div>
            <label className="flex min-h-11 cursor-pointer items-center justify-center rounded-xl border border-dashed border-green-700 px-3 text-sm font-semibold text-green-700 dark:border-green-500 dark:text-green-500">
              {t("takePhoto")}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                multiple
                className="sr-only"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 8))}
              />
            </label>
            {previews.length > 0 && (
              <>
                <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                  {files.length} {t("photosChosen")}
                </p>
                <ul className="mt-2 grid grid-cols-4 gap-2">
                  {previews.map((u, i) => (
                    <li key={u}>
                      <img src={u} alt={files[i]?.name ?? ""} className="aspect-square w-full rounded-lg object-cover" />
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button type="button" variant="ghost" onClick={getLocation} disabled={locState === "busy"}>
                {t("useLocation")}
              </Button>
              {locState === "ok" && loc && (
                <Chip tone="good">
                  {t("locationAdded")}: {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
                </Chip>
              )}
              {locState === "denied" && <Chip tone="warn">{t("locationDenied")}</Chip>}
            </div>
          </div>

          <Button type="submit" className="w-full" disabled={watched.running || !farmerId}>
            {watched.running ? t("running") : t("buildDossier")}
          </Button>
        </form>
      </Card>

      <LiveRunViewer run={watched.agentRun} running={watched.running} />
      {watched.error && <ErrorNote message={watched.error} onRetry={watched.start} />}

      {r && (
        <Card title={`${t("dossier")} ${r.claim_id}`}>
          <div className="rounded-xl bg-amber-50 p-2.5 text-xs font-medium text-amber-950 dark:bg-amber-900/30 dark:text-amber-100">
            {t("verifyBanner")}
          </div>
          {r.intimation_deadline && (
            <p className="mt-3 text-sm">
              {t("reportBy")} <b>{r.intimation_deadline}</b>
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            <Chip tone={r.confidence >= 0.85 ? "good" : "warn"}>
              {t("confidence")}: {Math.round(r.confidence * 100)}%
            </Chip>
          </div>
          {r.warnings.length > 0 && (
            <>
              <h3 className="mt-3 text-sm font-semibold">{t("warnings")}</h3>
              <ul className="list-inside list-disc break-words text-xs text-neutral-700 dark:text-neutral-300">
                {r.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </>
          )}
          {r.evidence[0]?.quote && (
            <>
              <h3 className="mt-3 text-sm font-semibold">{t("weatherEvidence")}</h3>
              <p className="text-sm italic">&ldquo;{r.evidence[0].quote}&rdquo;</p>
            </>
          )}
          <SourceList sources={r.evidence} />
          <a
            className="mt-4 flex min-h-11 items-center justify-center rounded-xl bg-green-700 text-sm font-semibold text-white"
            href={fileUrl(r.dossier_url)}
            target="_blank"
            rel="noreferrer noopener"
          >
            {t("openPdf")}
          </a>
        </Card>
      )}
    </div>
  );
}
