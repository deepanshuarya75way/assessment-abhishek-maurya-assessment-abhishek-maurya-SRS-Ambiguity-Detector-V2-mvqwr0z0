"use client";

/**
 * Score-over-time chart (Stage 11 — the ONLY Recharts consumer). A composed
 * area (average ambiguity score, fixed 0–100 axis — never a truncated axis
 * that exaggerates wiggles) + bars (runs per bucket, own count axis). Null
 * averages stay gaps (`connectNulls` off): an unscored bucket is missing
 * data, never a zero. The parent pairs this visual with a real legend, a
 * text summary, and a full data table — the chart is never the only way to
 * read the trend.
 */

import { useReducedMotionConfig } from "motion/react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  key: string;
  /** Short axis label ("Sep 1"). */
  label: string;
  /** Full tooltip/table label ("Sep 1" or "Week of Sep 1"). */
  fullLabel: string;
  avg: number | null;
  analyses: number;
  requirements: number;
}

function TrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: TrendPoint }>;
}) {
  const point = active === true ? payload?.[0]?.payload : undefined;
  if (point === undefined) return null;
  return (
    <div className="rounded-input border border-line bg-white px-3 py-2 shadow-lg">
      <p className="text-[13px] font-semibold text-ink">{point.fullLabel}</p>
      <p className="mt-1 font-mono text-xs text-ink-soft tabular-nums">
        {point.avg === null ? "No scored runs" : `Average score ${point.avg}`}
      </p>
      <p className="mt-0.5 font-mono text-xs text-ink-faint tabular-nums">
        {point.analyses} {point.analyses === 1 ? "run" : "runs"} · {point.requirements}{" "}
        {point.requirements === 1 ? "requirement" : "requirements"}
      </p>
    </div>
  );
}

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const reduceMotion = useReducedMotionConfig();
  return (
    <div className="h-64 sm:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={points}
          margin={{ top: 8, right: 4, bottom: 0, left: -12 }}
          barCategoryGap="35%"
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-line)" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            minTickGap={28}
            tick={{ fill: "var(--color-ink-faint)", fontSize: 12 }}
          />
          <YAxis
            yAxisId="score"
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            width={40}
            tick={{ fill: "var(--color-ink-faint)", fontSize: 12 }}
          />
          <YAxis
            yAxisId="runs"
            orientation="right"
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            width={32}
            tick={{ fill: "var(--color-ink-faint)", fontSize: 12 }}
          />
          <Tooltip content={<TrendTooltip />} />
          <Bar
            yAxisId="runs"
            dataKey="analyses"
            name="Runs"
            fill="var(--color-line)"
            isAnimationActive={!reduceMotion}
          />
          <Area
            yAxisId="score"
            type="monotone"
            dataKey="avg"
            name="Average score"
            stroke="var(--color-signal)"
            strokeWidth={2}
            fill="var(--color-signal)"
            fillOpacity={0.12}
            dot={{ r: 2, fill: "var(--color-signal)", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
            isAnimationActive={!reduceMotion}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
