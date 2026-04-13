import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
};

export function PageHeader({ title, subtitle, actions }: PageHeaderProps): JSX.Element {
  return (
    <div className="pw-section-header">
      <div>
        <h3 className="pw-section-title">{title}</h3>
        {subtitle ? <p className="pw-inline-note">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  );
}
