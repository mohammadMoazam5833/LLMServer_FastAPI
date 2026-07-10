import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = ["#8b5cf6", "#a78bfa", "#6366f1", "#10b981", "#f59e0b", "#f43f5e"];

function fmt(n: number) {
  return n.toLocaleString("fa-IR");
}

export default function UserShareChart({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  if (data.length === 0) {
    return <p className="text-zinc-400 text-center py-16">بدون داده</p>;
  }

  const total = data.reduce((s, d) => s + d.value, 0);

  return (
    <div className="flex flex-col lg:flex-row items-center gap-8 h-full min-h-[320px]">
      <div className="w-48 h-48 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={72}
              paddingAngle={3}
              strokeWidth={0}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => [fmt(Number(v)), "توکن"]} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <ul className="flex-1 w-full space-y-3">
        {data.map((d, i) => {
          const pct = total > 0 ? Math.round((d.value / total) * 100) : 0;
          return (
            <li key={d.name} className="flex items-center gap-3">
              <span
                className="w-3 h-3 rounded-full shrink-0"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className="flex-1 font-semibold text-zinc-800 truncate">{d.name}</span>
              <span className="text-sm text-zinc-500 tabular-nums shrink-0">{pct}٪</span>
              <span className="text-sm font-bold text-zinc-900 tabular-nums shrink-0 w-24 text-left">
                {fmt(d.value)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
