type MetricCardProps = {
  label: string;
  value: string | number;
  meta?: string;
};

export function MetricCard({ label, value, meta }: MetricCardProps): JSX.Element {
  return (
    <article className="pw-metric-card">
      <div className="pw-metric-label">{label}</div>
      <div className="pw-metric-value">{value}</div>
      {meta ? <div className="pw-metric-meta">{meta}</div> : null}
    </article>
  );
}
