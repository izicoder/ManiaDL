import type { Settings } from "../types";

export const STATUS_ORDER = [
  "ranked",
  "loved",
  "qualified",
  "pending",
  "graveyard",
] as const;

export const STATUS_LABELS: Record<string, string> = {
  ranked: "Ranked",
  loved: "Loved",
  qualified: "Qualified",
  pending: "Pending",
  graveyard: "Graveyard",
  any: "Any",
};

export const SORTS = [
  "favourites_desc",
  "plays_desc",
  "ranked_desc",
  "updated_desc",
  "difficulty_desc",
  "relevance_desc",
] as const;

export const SORT_LABELS: Record<string, string> = {
  favourites_desc: "Most favourites",
  plays_desc: "Most played",
  ranked_desc: "Recently ranked",
  updated_desc: "Recently updated",
  difficulty_desc: "Difficulty",
  relevance_desc: "Relevance",
};

export const ADVANCED_FIELDS: ReadonlyArray<{
  key: keyof Settings;
  label: string;
  hint?: string;
}> = [
  { key: "query", label: "Search query" },
  { key: "title", label: "Title contains" },
  { key: "artist", label: "Artist contains" },
  { key: "creator", label: "Mapper contains" },
  { key: "source", label: "Source contains" },
  { key: "exclude", label: "Exclude terms", hint: "comma-separated" },
  { key: "genre", label: "Genres", hint: "comma-separated, partial ok" },
  {
    key: "language",
    label: "Languages",
    hint: "comma-separated, partial ok",
  },
  { key: "bpm_range", label: "BPM range", hint: "e.g. 150-220" },
  { key: "length_range", label: "Length range (s)", hint: "e.g. 60-300" },
  { key: "notes_range", label: "Notes range", hint: "e.g. 1000-5000" },
  { key: "min_plays", label: "Min play count" },
  {
    key: "ranked_range",
    label: "Ranked dates",
    hint: "e.g. 2020-01-01..2024-12-31",
  },
];

export const DEFAULT_SETTINGS: Settings = {
  client_id: "",
  client_secret: "",
  out: "",
  statuses: "ranked",
  keys: "all",
  min_sr: "0",
  max_sr: "99",
  min_favs: "0",
  sort: "favourites_desc",
  limit: "500",
  workers: "4",
  batch: "20",
  advanced: false,
  query: "",
  title: "",
  artist: "",
  creator: "",
  source: "",
  exclude: "",
  genre: "",
  language: "",
  bpm_range: "",
  length_range: "",
  notes_range: "",
  min_plays: "0",
  ranked_range: "",
  include_nsfw: false,
};

const ADVANCED_TEXT_KEYS: ReadonlyArray<keyof Settings> = [
  "query",
  "title",
  "artist",
  "creator",
  "source",
  "exclude",
  "genre",
  "language",
  "bpm_range",
  "length_range",
  "notes_range",
  "ranked_range",
];

/** Fill missing keys so older configs still render every control. */
export function normaliseSettings(
  incoming: Partial<Settings> | null | undefined,
): Settings {
  const merged = { ...DEFAULT_SETTINGS, ...(incoming ?? {}) } as Settings;
  for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    const value = merged[key];
    if (typeof DEFAULT_SETTINGS[key] === "boolean") {
      (merged as unknown as Record<string, unknown>)[key] = Boolean(value);
    } else if (typeof value !== "string") {
      (merged as unknown as Record<string, unknown>)[key] =
        value == null ? "" : String(value);
    }
  }
  return merged;
}

/**
 * B10.2: the advanced section turns itself on when the saved config already
 * carries advanced values, so they are never silently ignored.
 */
export function autoEnableAdvanced(settings: Settings): boolean {
  if (settings.advanced) {
    return true;
  }
  const hasText = ADVANCED_TEXT_KEYS.some(
    (key) => String(settings[key] ?? "").trim() !== "",
  );
  const minPlays = Number.parseInt(String(settings.min_plays || "0"), 10);
  return hasText || (Number.isFinite(minPlays) && minPlays > 0);
}

export function parseStatuses(raw: string): string[] {
  const parts = String(raw || "")
    .split(",")
    .map((part) => part.trim().toLowerCase())
    .filter((part) => part.length > 0);
  if (parts.length === 0 || parts.includes("any")) {
    return ["any"];
  }
  const known = STATUS_ORDER.filter((name) => parts.includes(name));
  return known.length > 0 ? known : ["ranked"];
}

/** Status checkbox rules from B10.2. */
export function toggleStatus(current: string[], name: string): string[] {
  if (name === "any") {
    return ["any"];
  }
  const withoutAny = current.filter((item) => item !== "any");
  const next = withoutAny.includes(name)
    ? withoutAny.filter((item) => item !== name)
    : [...withoutAny, name];
  const ordered = STATUS_ORDER.filter((item) => next.includes(item));
  return ordered.length > 0 ? ordered : ["ranked"];
}

export function statusesToRaw(statuses: string[]): string {
  if (statuses.includes("any")) {
    return "any";
  }
  const ordered = STATUS_ORDER.filter((name) => statuses.includes(name));
  return (ordered.length > 0 ? ordered : ["ranked"]).join(",");
}
