import { BENCHMARKS, isToy } from "@/lib/model";

const label = (b: string) => BENCHMARKS.find((x) => x.id === b)?.label.replace(" (toy)", "") ?? b;

// The line every working page shows on a toy benchmark.
export function ToyNote({ benchmark }: { benchmark: string }) {
  if (!isToy(benchmark)) return null;
  return (
    <section className="wrap" style={{ paddingBottom: 24 }}>
      <p className="toy-note"><span className="toy-tag">Toy example</span> {label(benchmark)}: only a few detectors were run, on a few datasets. The full set of scores is not available.</p>
    </section>
  );
}

