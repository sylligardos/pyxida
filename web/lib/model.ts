// Types, constants and URL state shared by server and client code.

export type Kind = "uni" | "multi";
export const KINDS: Kind[] = ["uni", "multi"];
export const KIND_LABEL: Record<Kind, string> = { uni: "Univariate", multi: "Multivariate" };

export const YOUR_DATA = "yours";
export const BENCHMARKS = [
  { id: "tsb-ad", label: "TSB-AD" },
  { id: "tsb-uad", label: "TSB-UAD" },
  { id: "timeeval", label: "TimeEval (toy)" },
  { id: "tab", label: "TAB (toy)" },
  { id: "mtsbench", label: "mTSBench (toy)" },
  { id: YOUR_DATA, label: "Run on your data" },
];
// Toy examples: a few fast detectors on a few datasets, not the full scores.
export const TOY = new Set(["timeeval", "tab", "mtsbench"]);
export const isToy = (benchmark: string) => TOY.has(benchmark);
export const DEFAULT_BENCHMARK = "tsb-ad";

export type State = { benchmark: string; kind: Kind };

export type SeriesMeta = { file: string; dataset: string; type: string; n: number | null; anomalies: number | null; channels?: number };
export type Summary = {
  benchmark: string;
  label: string;
  kind: Kind;
  toy?: boolean;
  n_series: number;
  n_datasets: number;
  n_detectors: number;
  n_anomalies: number;
  n_points: number;
  detectors: string[];
  demo_series: string | null;
  series: SeriesMeta[];
};
export type Series = { file: string; n: number; values: number[]; labels: [number, number][] };

type Params = Record<string, string | string[] | undefined>;

export function stateFrom(params: Params): State {
  const b = typeof params.b === "string" ? params.b : DEFAULT_BENCHMARK;
  const k = params.k === "multi" ? "multi" : "uni";
  return { benchmark: BENCHMARKS.some((x) => x.id === b) ? b : DEFAULT_BENCHMARK, kind: k };
}

export function href(pathname: string, state: State, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams({ b: state.benchmark, k: state.kind, ...extra });
  return `${pathname}?${q}`;
}

export type Landscape = {
  detectors: string[];
  metrics: { aucpr: { label: string }; vus: { label: string; buffer: number } };
  rows: (SeriesMeta & { aucpr: (number | null)[]; vus: (number | null)[] })[];
};

// Where the browser fetches data files from. Locally the API route below;
// online the object storage base URL.
export const DATA_URL = process.env.NEXT_PUBLIC_DATA_URL ?? "/api/data";

export const stem = (file: string) => file.replace(/\.csv$/, "");

export type SeriesDoc = {
  file: string; n: number; labels: [number, number][];
  values?: number[];
  n_channels?: number; channels?: { name: string; values: number[] }[];
};

export type KSet = { top: number | null; top_dets: string[]; best: number; best_dets: string[] };
export type Redundancy = {
  buffer: number;
  detectors: string[]; mean_vus: (number | null)[];
  agree: { global: (number | null)[][]; datasets: Record<string, (number | null)[][]>; n: Record<string, number> };
  // Per dataset: its files, and per pair "a-b" (a < b) the best series as [file index, tau].
  examples: Record<string, { files: string[]; pairs: Record<string, [number, number][]> }>;
  series: { file: string; dataset: string; best1: number; best1_det: string; k2?: KSet; k3?: KSet; agree: { top5: number; all: number } | null }[];
};

// The series graph (scripts/export_graph.py): one graph per scope and metric.
export type GraphScope = { key: string; group: "all" | "dataset" | "type"; value: string; n: number };
export type GraphData = {
  files?: string[]; nodes: [number, number][]; edges: [number, number, number][];
  community: number[];   // one per node, numbered by size, largest first; the last may be the merged small ones
  n_detectors?: number; dropped_series: string[]; dropped_detectors: string[];
};
export type Graph = {
  k: number;
  metrics: Landscape["metrics"];
  anomaly_len: Record<string, number | null>;   // mean anomaly length per series
  scopes: GraphScope[];
  graphs: Record<string, Record<"aucpr" | "vus", GraphData>>;
};
