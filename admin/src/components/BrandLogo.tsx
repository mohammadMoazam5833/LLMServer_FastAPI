type Size = "sm" | "md" | "lg";

const sizes: Record<Size, { box: string; icon: string }> = {
  sm: { box: "w-9 h-9 rounded-lg", icon: "w-5 h-5" },
  md: { box: "w-11 h-11 rounded-xl", icon: "w-6 h-6" },
  lg: { box: "w-14 h-14 rounded-2xl", icon: "w-8 h-8" },
};

function GatewayIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3v4M12 17v4M3 12h4M17 12h4"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="3.25" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="5" cy="5" r="2" fill="currentColor" opacity="0.85" />
      <circle cx="19" cy="5" r="2" fill="currentColor" opacity="0.85" />
      <circle cx="5" cy="19" r="2" fill="currentColor" opacity="0.85" />
      <circle cx="19" cy="19" r="2" fill="currentColor" opacity="0.85" />
      <path
        d="M7 6.5L9.8 9.8M16.2 9.8L17 7M7 17.5L9.8 14.2M16.2 14.2L17 17"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        opacity="0.7"
      />
    </svg>
  );
}

export function BrandMark({ size = "md" }: { size?: Size }) {
  const s = sizes[size];
  return (
    <div
      className={`${s.box} shrink-0 bg-gradient-to-br from-violet-500 via-violet-600 to-indigo-700 text-white flex items-center justify-center shadow-lg shadow-violet-900/30 ring-1 ring-white/10`}
    >
      <GatewayIcon className={s.icon} />
    </div>
  );
}

export function BrandTitle({ compact = false }: { compact?: boolean }) {
  return (
    <div className="min-w-0">
      <p className={`font-black text-white leading-tight tracking-tight ${compact ? "text-[15px]" : "text-[17px]"}`}>
        LLM Gateway
      </p>
      <p className={`text-zinc-500 mt-0.5 ${compact ? "text-[11px]" : "text-xs"}`}>پنل مدیریت</p>
    </div>
  );
}

export default function BrandLogo({ size = "md" }: { size?: Size }) {
  return (
    <div className="flex items-center gap-3">
      <BrandMark size={size} />
      <BrandTitle />
    </div>
  );
}
