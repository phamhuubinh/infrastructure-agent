import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type OrionIconProps = HTMLAttributes<HTMLSpanElement>;

export function OrionIcon({ className, ...props }: OrionIconProps) {
  return (
    <span aria-hidden="true" className={cn("relative inline-block", className)} {...props}>
      <img
        src="/orion-icon-light.png"
        alt=""
        draggable={false}
        className="absolute inset-0 h-full w-full object-contain dark:hidden"
      />
      <img
        src="/orion-icon-dark.png"
        alt=""
        draggable={false}
        className="absolute inset-0 hidden h-full w-full object-contain dark:block"
      />
    </span>
  );
}
