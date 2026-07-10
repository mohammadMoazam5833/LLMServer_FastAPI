export default function PageHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-8">
      <h2 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h2>
      {subtitle && (
        <p className="text-slate-500 mt-2 text-sm leading-relaxed">{subtitle}</p>
      )}
    </div>
  );
}
