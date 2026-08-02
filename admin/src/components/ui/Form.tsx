import { type ReactNode, type ButtonHTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { Card, CardBody, CardHeader } from "./Card";

export function FormCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <Card className="w-full">
      <CardHeader title={title} subtitle={subtitle} />
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function FormField({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 ${className}`}>
      <span className="flex min-h-5 items-center gap-1.5 text-xs font-bold leading-5 text-slate-700">
        {label}
        {hint && (
          <span className="truncate text-[10px] font-medium text-slate-400" title={hint}>
            · {hint}
          </span>
        )}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full h-11 bg-white border border-slate-200 rounded-xl px-3.5 text-sm text-slate-900 placeholder:text-slate-400 shadow-[0_1px_2px_rgba(15,23,42,.02)] transition-all hover:border-slate-300 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 disabled:bg-slate-50 disabled:text-slate-400";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={inputClass} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={inputClass} {...props} />;
}

export function PrimaryButton({
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 text-sm font-bold text-white shadow-sm shadow-indigo-600/20 transition-all hover:-translate-y-px hover:bg-indigo-700 hover:shadow-md disabled:pointer-events-none disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-transparent px-3 text-xs font-bold text-slate-600 transition-colors hover:border-slate-200 hover:bg-slate-50 hover:text-slate-900 disabled:pointer-events-none disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function FormRow({ children }: { children: ReactNode }) {
  return (
    <div className="grid w-full grid-cols-1 items-end gap-x-4 gap-y-4 md:grid-cols-12">
      {children}
    </div>
  );
}

export function FormCol({ children, span = 3 }: { children: ReactNode; span?: 2 | 3 | 4 | 5 | 6 | 8 | 9 | 12 }) {
  const spanClass: Record<number, string> = {
    2: "md:col-span-2",
    3: "md:col-span-3",
    4: "md:col-span-4",
    5: "md:col-span-5",
    6: "md:col-span-6",
    8: "md:col-span-8",
    9: "md:col-span-9",
    12: "md:col-span-12",
  };
  return <div className={`min-w-0 ${spanClass[span]}`}>{children}</div>;
}

export function FormSubmitCol({ children, span = 3 }: { children: ReactNode; span?: 2 | 3 | 4 | 5 | 6 | 12 }) {
  const spanClass: Record<number, string> = {
    2: "md:col-span-2",
    3: "md:col-span-3",
    4: "md:col-span-4",
    5: "md:col-span-5",
    6: "md:col-span-6",
    12: "md:col-span-12",
  };
  return (
    <div className={`min-w-0 ${spanClass[span]}`}>
      <div className="flex h-full min-h-[68px] items-end">
        {children}
      </div>
    </div>
  );
}
