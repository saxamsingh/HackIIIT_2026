import { useCallback, useEffect, useState } from "react";
import { fileUrl, getSchemes, type SchemesResponse } from "../api";
import { Button, Card, Chip, ErrorNote, SourceList } from "../components/ui";
import { rupees, safeHref } from "../format";
import { docLabel, useI18n } from "../i18n";

export function Schemes({ farmerId }: { farmerId: string | undefined }) {
  const { t } = useI18n();
  const [data, setData] = useState<SchemesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getSchemes(farmerId)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [farmerId]);
  useEffect(load, [load]);

  const schemes = data?.schemes ?? [];
  return (
    <div className="space-y-4">
      <Button variant="ghost" className="w-full" onClick={load} disabled={loading}>
        {loading ? t("running") : t("checkSchemes")}
      </Button>
      {error && <ErrorNote message={error} onRetry={load} />}
      {data && schemes.length === 0 && (
        <Card title={t("noSchemesTitle")}>
          <p className="text-sm">{data.note}</p>
        </Card>
      )}
      {schemes.map((m) => (
        <Card key={m.scheme_id}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-semibold">{m.name}</h3>
            <Chip tone={m.eligible ? "good" : m.needs_info.length ? "warn" : "bad"}>
              {m.eligible ? t("eligible") : m.needs_info.length ? t("needsInfo") : t("notEligible")}
            </Chip>
          </div>
          <p className="mt-1 text-sm">{m.benefit}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Chip tone={m.deadline ? "warn" : "neutral"}>
              {m.deadline ? `${t("deadline")}: ${m.deadline}` : t("noDeadline")}
            </Chip>
            {m.estimated_value_rs != null && (
              <Chip>
                {t("valueRs")}: {rupees(m.estimated_value_rs)}
              </Chip>
            )}
          </div>
          {m.missing_docs.length > 0 && (
            <p className="mt-2 text-xs text-amber-900 dark:text-amber-200">
              {t("missingDocs")}: {m.missing_docs.map((d) => docLabel(t, d)).join(", ")}
            </p>
          )}
          <ul className="mt-2 list-inside list-disc text-xs text-neutral-600 dark:text-neutral-400">
            {m.reasons.map((x) => (
              <li key={x}>{x}</li>
            ))}
            {m.needs_info.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            {m.packet_url && (
              <a
                className="inline-flex min-h-11 items-center rounded-xl bg-green-700 px-4 text-sm font-semibold text-white"
                href={fileUrl(m.packet_url)}
                target="_blank"
                rel="noreferrer noopener"
                download
              >
                {t("packet")}
              </a>
            )}
            {safeHref(m.apply_url) && (
              <a
                className="inline-flex min-h-11 items-center rounded-xl border border-green-700 px-4 text-sm font-semibold text-green-700 dark:border-green-500 dark:text-green-500"
                href={safeHref(m.apply_url)}
                target="_blank"
                rel="noreferrer noopener"
              >
                {t("apply")}
              </a>
            )}
          </div>
          <SourceList sources={m.evidence} />
        </Card>
      ))}
    </div>
  );
}
