type MetricCardProps = {
  label: string;
  value: string | number;
  meta?: string;
  className?: string;
};

export function MetricCard({ label, value, meta, className }: MetricCardProps): JSX.Element {
  return (
    <article className={`pw-metric-card${className ? ` ${className}` : ""}`}>
      <div className="pw-metric-label">{label}</div>
      <div className="pw-metric-value">{value}</div>
      {meta ? <div className="pw-metric-meta">{meta}</div> : null}
    </article>
  );
}
