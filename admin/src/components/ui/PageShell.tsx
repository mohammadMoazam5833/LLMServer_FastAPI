import { type ReactNode } from "react";

/** تمام عرض محتوای اصلی — بدون max-width */
export default function PageShell({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`w-full space-y-8 ${className}`}>{children}</div>
  );
}
