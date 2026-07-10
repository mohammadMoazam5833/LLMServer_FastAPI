export interface KeyUsageItem {
  id: string;
  title: string;
  subtitle: string;
  used: number;
  quota: number;
  percent: number;
}

function fmt(n: number) {
  return n.toLocaleString("fa-IR");
}

function barColor(percent: number) {
  if (percent >= 90) return "from-rose-500 to-rose-400";
  if (percent >= 70) return "from-amber-500 to-amber-400";
  return "from-violet-600 to-violet-400";
}

function badgeColor(percent: number) {
  if (percent >= 90) return "bg-rose-50 text-rose-600";
  if (percent >= 70) return "bg-amber-50 text-amber-700";
  return "bg-violet-50 text-violet-700";
}

function KeyRow({
  item,
  rank,
  maxVal,
}: {
  item: KeyUsageItem;
  rank: number;
  maxVal: number;
}) {
  const usedW = Math.max(3, (item.used / maxVal) * 100);
  const quotaW = item.quota > 0 ? Math.max(3, (item.quota / maxVal) * 100) : 0;

  return (
    <div className="rounded-xl border border-zinc-100 bg-zinc-50/50 px-4 py-3.5 hover:border-violet-200 hover:bg-violet-50/30 transition-colors">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-start gap-3 min-w-0">
          <span className="shrink-0 w-8 h-8 rounded-lg bg-white border border-zinc-200 text-violet-600 text-xs font-black flex items-center justify-center tabular-nums shadow-sm">
            {(rank + 1).toLocaleString("fa-IR")}
          </span>
          <div className="min-w-0">
            <p className="font-bold text-zinc-900 truncate" title={item.title}>
              {item.title}
            </p>
            <p className="text-xs text-zinc-400 mt-0.5">{item.subtitle}</p>
          </div>
        </div>
        <div className="text-left shrink-0 flex flex-col items-end gap-1">
          <span className={`text-[11px] font-bold px-2 py-0.5 rounded ${badgeColor(item.percent)}`}>
            {item.percent.toLocaleString("fa-IR")}٪
          </span>
          <p className="text-sm font-black text-zinc-900 tabular-nums">{fmt(item.used)}</p>
          <p className="text-[11px] text-zinc-400 tabular-nums">
            از {item.quota > 0 ? fmt(item.quota) : "∞"}
          </p>
        </div>
      </div>

      <div className="relative h-2.5 bg-white border border-zinc-100 rounded-full overflow-hidden">
        {quotaW > 0 && (
          <div
            className="absolute inset-y-0 right-0 bg-zinc-200/70 rounded-full"
            style={{ width: `${quotaW}%` }}
          />
        )}
        <div
          className={`absolute inset-y-0 right-0 rounded-full bg-gradient-to-l ${barColor(item.percent)} transition-all duration-500 shadow-sm`}
          style={{ width: `${usedW}%` }}
        />
      </div>
    </div>
  );
}

export default function UsageKeyChart({
  items,
  maxHeight = false,
}: {
  items: KeyUsageItem[];
  /** ارتفاع ثابت + اسکرول داخلی */
  maxHeight?: number | false;
}) {
  if (items.length === 0) {
    return <p className="text-center text-zinc-400 py-16">هنوز مصرفی ثبت نشده</p>;
  }

  const maxVal = Math.max(...items.map((i) => Math.max(i.used, i.quota, 1)));

  const rows = items.map((item, rank) => (
    <KeyRow key={item.id} item={item} rank={rank} maxVal={maxVal} />
  ));

  if (!maxHeight) {
    return <div className="space-y-4">{rows}</div>;
  }

  return (
    <div className="overflow-y-auto pr-1 -mr-1 space-y-4" style={{ maxHeight }}>
      {rows}
    </div>
  );
}
