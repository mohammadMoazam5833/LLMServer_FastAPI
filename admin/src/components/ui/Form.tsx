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

/** فقط label + input — بدون hint زیر input تا ردیف به‌هم نریزد */
export function FormField({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-2 min-w-0 ${className}`}>
      <span className="text-sm font-semibold text-zinc-700 leading-5 truncate">{label}</span>
      {children}
    </div>
  );
}

const inputClass =
  "w-full h-11 bg-zinc-50 border border-zinc-200 rounded-lg px-4 text-sm text-zinc-900 placeholder:text-zinc-400 transition-all focus:outline-none focus:bg-white focus:border-violet-500 focus:ring-2 focus:ring-violet-500/15";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={inputClass} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={inputClass} {...props} />;
}

export function PrimaryButton({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 h-11 bg-violet-600 hover:bg-violet-700 text-white rounded-lg px-5 text-sm font-bold disabled:opacity-50 transition-colors ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex items-center justify-center h-10 rounded-lg px-4 text-sm font-medium text-zinc-600 hover:bg-zinc-100 transition-colors ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function FormRow({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-12 gap-x-5 gap-y-4 items-end w-full">
      {children}
    </div>
  );
}

export function FormCol({ children, span = 3 }: { children: ReactNode; span?: 2 | 3 | 4 | 5 | 6 | 12 }) {
  const spanClass: Record<number, string> = {
    2: "xl:col-span-2", 3: "xl:col-span-3", 4: "xl:col-span-4",
    5: "xl:col-span-5", 6: "xl:col-span-6", 12: "xl:col-span-12",
  };
  return <div className={`min-w-0 ${spanClass[span]}`}>{children}</div>;
}

/** دکمه submit در همان ردیف فیلدها — با label نامرئی هم‌تراز می‌شود */
export function FormSubmitCol({ children, span = 3 }: { children: ReactNode; span?: 2 | 3 | 4 }) {
  const spanClass: Record<number, string> = { 2: "xl:col-span-2", 3: "xl:col-span-3", 4: "xl:col-span-4" };
  return (
    <div className={`min-w-0 ${spanClass[span]}`}>
      <div className="flex flex-col gap-2">
        <span className="text-sm font-semibold leading-5 invisible select-none" aria-hidden>—</span>
        {children}
      </div>
    </div>
  );
}
