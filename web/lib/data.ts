// Where the demo's data comes from. Locally, the files scripts/export_web.py
// writes under data/web/; online, the same paths in object storage.
// Server only: it reads the filesystem.

import { promises as fs } from "fs";
import path from "path";
import { Kind, Landscape, Redundancy, Series, SeriesDoc, State, Summary, YOUR_DATA } from "./model";

export * from "./model";

export const DATA_ROOT = process.env.PYXIDA_DATA ?? path.join(process.cwd(), "..", "data", "web");

async function readJson<T>(...parts: string[]): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(path.join(DATA_ROOT, ...parts), "utf8")) as T;
  } catch {
    return null;
  }
}

export async function loadSummary(state: State): Promise<Summary | null> {
  if (state.benchmark === YOUR_DATA) return null;
  return readJson<Summary>(state.benchmark, state.kind, "summary.json");
}

export async function loadSeries(state: State, file: string): Promise<Series | null> {
  const stem = file.replace(/\.csv$/, "");
  const doc = await readJson<SeriesDoc>(state.benchmark, state.kind, "series", `${stem}.json`);
  if (!doc) return null;
  const values = doc.values ?? doc.channels?.[0]?.values ?? [];
  return { file: doc.file, n: doc.n, values, labels: doc.labels };
}

export async function hasKind(benchmark: string, kind: Kind): Promise<boolean> {
  try {
    await fs.access(path.join(DATA_ROOT, benchmark, kind, "summary.json"));
    return true;
  } catch {
    return false;
  }
}

export const fmt = (n: number) => n.toLocaleString("en-US");
export const fmtM = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M` : fmt(n));

export async function loadLandscape(state: State): Promise<Landscape | null> {
  if (state.benchmark === YOUR_DATA) return null;
  return readJson<Landscape>(state.benchmark, state.kind, "landscape.json");
}

export async function loadRedundancy(state: State): Promise<Redundancy | null> {
  if (state.benchmark === YOUR_DATA) return null;
  return readJson<Redundancy>(state.benchmark, state.kind, "redundancy.json");
}
