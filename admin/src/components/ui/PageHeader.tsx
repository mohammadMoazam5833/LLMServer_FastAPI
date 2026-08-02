import { type ReactNode } from "react";

export default function PageHeader({
  title,
  subtitle,
  eyebrow,
  action,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        {eyebrow && (
          <p className="mb-2 text-[11px] font-extrabold tracking-[0.12em] text-indigo-600 uppercase">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-black tracking-[-0.025em] text-slate-950 sm:text-[28px]">{title}</h1>
        {subtitle && (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{subtitle}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
