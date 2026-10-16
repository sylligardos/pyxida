// Where the demo's data comes from. Locally, the files scripts/export_web.py
// writes under data/web/; online, the same paths in object storage.
// Server only: it reads the filesystem.

import { promises as fs } from "fs";
import path from "path";
import { BENCHMARKS, BENCHMARK_ID, Kind, Landscape, Redundancy, Series, SeriesDoc, State, Summary, YOUR_DATA } from "./model";

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

// The menu: the shipped benchmarks, then any other benchmark exported under
// DATA_ROOT (named by its summary's label), then "Run on your data".
export async function listBenchmarks(): Promise<{ id: string; label: string }[]> {
  let dirs: string[] = [];
  try {
    dirs = (await fs.readdir(DATA_ROOT, { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name);
  } catch { /* no data yet */ }
  const extra = dirs.filter((d) => BENCHMARK_ID.test(d) && d !== YOUR_DATA && !BENCHMARKS.some((b) => b.id === d)).sort();
  const found = await Promise.all(extra.map(async (id) => {
    const s = (await readJson<Summary>(id, "uni", "summary.json")) ?? (await readJson<Summary>(id, "multi", "summary.json"));
    return s ? { id, label: s.label ?? id } : null;
  }));
  const shipped = BENCHMARKS.filter((b) => b.id !== YOUR_DATA);
  const yours = BENCHMARKS.filter((b) => b.id === YOUR_DATA);
  return [...shipped, ...found.filter((b): b is { id: string; label: string } => b !== null), ...yours];
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
