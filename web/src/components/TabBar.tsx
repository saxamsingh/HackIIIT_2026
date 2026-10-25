import { useI18n, type Key } from "../i18n";

export type Tab = "home" | "sell" | "schemes" | "claim" | "ledger" | "operator";

const TABS: { id: Tab; label: Key; icon: string }[] = [
  { id: "home", label: "tabHome", icon: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { id: "sell", label: "tabSell", icon: "M4 7h16l-1.5 11a2 2 0 0 1-2 1.7H7.5a2 2 0 0 1-2-1.7zM8 7a4 4 0 0 1 8 0" },
  { id: "schemes", label: "tabSchemes", icon: "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6" },
  { id: "claim", label: "tabClaim", icon: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4" },
  { id: "ledger", label: "tabLedger", icon: "M5 4h14v16H5zM9 9h6M9 13h6M9 17h3" },
];

export function TabBar({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  const { t } = useI18n();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-stone-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur dark:border-white/10 dark:bg-neutral-900/95"
    >
      <ul className="mx-auto flex max-w-md">
        {TABS.map((x) => {
          const active = x.id === tab;
          return (
            <li key={x.id} className="flex-1">
              <button
                onClick={() => onChange(x.id)}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
                  active ? "text-green-700 dark:text-green-500" : "text-neutral-500"
                }`}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={x.icon} />
                </svg>
                {t(x.label)}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
