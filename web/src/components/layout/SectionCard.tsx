import { PropsWithChildren, type ReactNode } from "react";

type SectionCardProps = PropsWithChildren<{
  title?: string;
  actions?: ReactNode;
  className?: string;
}>;

export function SectionCard({ title, actions, className, children }: SectionCardProps): JSX.Element {
  return (
    <section className={`pw-panel pw-section${className ? ` ${className}` : ""}`}>
      {title ? (
        <div className="pw-section-header">
          <div>
            <h3 className="pw-section-title">{title}</h3>
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
