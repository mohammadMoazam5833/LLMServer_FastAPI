import { type ReactNode } from "react";

const tones = {
  violet: "bg-indigo-50 text-indigo-600 ring-indigo-100",
  zinc: "bg-slate-100 text-slate-700 ring-slate-200",
  emerald: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  amber: "bg-amber-50 text-amber-600 ring-amber-100",
} as const;

export default function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "violet",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: ReactNode;
  tone?: keyof typeof tones;
}) {
  return (
    <div className="group flex w-full items-center gap-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,.03)] transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/40">
      <div className={`flex size-11 shrink-0 items-center justify-center rounded-xl text-lg ring-1 ${tones[tone]}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-slate-500">{label}</p>
        <p className="mt-1 text-2xl font-black tracking-tight text-slate-950 tabular-nums">{value}</p>
        {hint && <p className="mt-1 truncate text-[11px] text-slate-400">{hint}</p>}
      </div>
    </div>
  );
}
