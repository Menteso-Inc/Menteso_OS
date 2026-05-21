import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

const badgeVariants = cva("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", {
  variants: {
    variant: {
      default: "bg-accent text-accent-foreground",
      success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
      warning: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
      danger: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

export interface BadgeProps extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

