import { useState } from "react";
import { confirmEntry } from "../api";
import { useI18n } from "../i18n";
import { Button, ErrorNote } from "./ui";

/** The farmer's explicit yes. Confirming counts the ledger entry; it never submits anything anywhere. */
export function ConfirmBar({ entryId, onConfirmed }: { entryId: string; onConfirmed: () => void }) {
  const { t } = useI18n();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setState("busy");
    setError(null);
    try {
      await confirmEntry(entryId);
      setState("done");
      onConfirmed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("idle");
    }
  };

  return (
    <div className="mt-4 space-y-2">
      <Button className="w-full" onClick={go} disabled={state !== "idle"}>
        {state === "done" ? `✓ ${t("confirmed")}` : state === "busy" ? t("confirming") : t("confirmPlan")}
      </Button>
      <p className="text-xs text-neutral-600 dark:text-neutral-400">{t("confirmNote")}</p>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
