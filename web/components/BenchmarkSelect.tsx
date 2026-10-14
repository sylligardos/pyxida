"use client";

import { usePathname, useRouter } from "next/navigation";

// The benchmark menu. Picking a benchmark keeps the page and the kind;
// "Run on your data" opens the Intro's how-to section.
export function BenchmarkSelect({
  value, kind, options, yours,
}: { value: string; kind: string; options: { id: string; label: string }[]; yours: string }) {
  const router = useRouter();
  const pathname = usePathname();
  return (
    <select
      aria-label="Benchmark"
      value={value}
      onChange={(e) => {
        const b = e.target.value;
        if (b === yours) router.push(`/?b=${value}&k=${kind}#your-data`);
        else router.push(`${pathname}?b=${b}&k=${kind}`);
      }}
    >
      {options.map((o) => (
        <option key={o.id} value={o.id}>{o.label}</option>
      ))}
    </select>
  );
}
