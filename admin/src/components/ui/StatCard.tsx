import { type ReactNode } from "react";

const tones = {
  violet: "bg-violet-500",
  zinc: "bg-zinc-900",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
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
    <div className="w-full bg-white rounded-xl border border-zinc-200/80 p-5 flex items-center gap-4">
      <div className={`shrink-0 w-10 h-10 rounded-lg ${tones[tone]} text-white flex items-center justify-center text-lg`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm text-zinc-500">{label}</p>
        <p className="text-2xl font-black text-zinc-900 tabular-nums tracking-tight mt-0.5">{value}</p>
        {hint && <p className="text-xs text-zinc-400 mt-1 truncate">{hint}</p>}
      </div>
    </div>
  );
}
