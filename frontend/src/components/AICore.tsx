import { cn } from "@/lib/utils";

export type CoreState = "idle" | "thinking" | "speaking" | "error" | "offline";

/** Lightweight CSS-only animated core. Speed and hue follow the assistant's state. */
export function AICore({
  state,
  size = 220,
  className,
}: {
  state: CoreState;
  size?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("core shrink-0", className)}
      data-state={state}
      style={{ width: size }}
      aria-hidden
    >
      <div className="core-halo" />
      <div className="core-ring r1" />
      <div className="core-ring r2" />
      <div className="core-ring r3" />
      <div className="core-ring r4" />
      <div className="core-heart" />
    </div>
  );
}
