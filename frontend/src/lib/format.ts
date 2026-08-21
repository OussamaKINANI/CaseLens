const absoluteFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const relativeFormatter = new Intl.RelativeTimeFormat("en-US", {
  numeric: "always",
  style: "narrow",
});

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function formatDate(value: string): string {
  return absoluteFormatter.format(new Date(value));
}

export function formatRelativeDate(value: string): string {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const magnitude = Math.abs(seconds);

  if (magnitude < 60) {
    return "just now";
  }

  for (const [unit, unitSeconds] of RELATIVE_UNITS) {
    if (magnitude >= unitSeconds) {
      return relativeFormatter.format(Math.trunc(seconds / unitSeconds), unit);
    }
  }

  return "just now";
}

export function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }

  return `${(value / 1024).toFixed(1)} KB`;
}

export function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
