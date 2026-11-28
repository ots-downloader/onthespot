import { Badge, Card } from "./ui";
import React, { ReactNode } from "react";

interface PageHeaderProps {
  icon: ReactNode;
  title: string;
  badge?: {
    label: string;
    variant: "neutral" | "success" | "warning" | "error" | "info";
  };
  description?: string;
  actions?: ReactNode;
  bottomContent?: ReactNode;
  id?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  icon,
  title,
  badge,
  description,
  actions,
  bottomContent,
  id,
}) => {
  return (
    <Card padding={4} elevation="low" id={id}>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-raised flex items-center justify-center text-fg-muted shrink-0">
            {icon}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-fg">
                {title}
              </h2>
              {badge && (
                <Badge variant={badge.variant} label={badge.label} />
              )}
            </div>
            {description && (
              <p className="text-xs text-fg-muted mt-0.5">
                {description}
              </p>
            )}
          </div>
        </div>

        {actions && (
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            {actions}
          </div>
        )}
      </div>

      {bottomContent && (
        <div className="mt-4 pt-3 border-t border-line">
          {bottomContent}
        </div>
      )}
    </Card>
  );
};
