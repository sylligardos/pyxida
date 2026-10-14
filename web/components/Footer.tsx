// A one-line footer: the takeaway in small type, nothing else. The pages
// still pass their takeaway and actions; the actions are not shown for now.

export function Footer({ takeaway }: { takeaway: string; children?: React.ReactNode }) {
  return (
    <footer className="footer">
      <div className="wrap">
        <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>Pyxida</span>
        <span style={{ fontSize: 13, color: "var(--text-3)" }}>{takeaway}</span>
      </div>
    </footer>
  );
}
