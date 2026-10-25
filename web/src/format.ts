/** Indian digit grouping (12,34,567) with the rupee sign. */
export function rupees(n: number): string {
  const v = Math.round(n);
  return `${v < 0 ? "-" : ""}₹${new Intl.NumberFormat("en-IN").format(Math.abs(v))}`;
}

export function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const todayIso = (): string => new Date().toISOString().slice(0, 10);

/** Only http(s) links from the backend are ever rendered as anchors. */
export const safeHref = (u: string | null | undefined): string | undefined =>
  u && /^https?:\/\//i.test(u) ? u : undefined;

export function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** A TinyFish live-view URL is only ever framed over https; anything else is ignored. */
export function frameableUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}
