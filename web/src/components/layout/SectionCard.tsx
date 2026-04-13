import { PropsWithChildren, type ReactNode } from "react";

type SectionCardProps = PropsWithChildren<{
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
}>;

export function SectionCard({ title, subtitle, actions, children }: SectionCardProps): JSX.Element {
  return (
    <section className="pw-panel pw-section">
      {title ? (
        <div className="pw-section-header">
          <div>
            <h3 className="pw-section-title">{title}</h3>
            {subtitle ? <p className="pw-inline-note">{subtitle}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
