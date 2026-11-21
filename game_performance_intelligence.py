#!/usr/bin/env python3
"""
Game Performance Intelligence & Stutter Detection System
A documented extension inspired by bm01/PerfAnalyzer.
Original repository: https://github.com/bm01/PerfAnalyzer
Original project copyright/licensing remains with its author (Apache-2.0).
This implementation adds target-FPS analysis, 1% low FPS, severity labels,
CSV/JSON exports, and automatic recommendations.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

PREFIX = "[PerfCounters]"
PAIR_RE = re.compile(r"^(.*?)\s+([0-9]+(?:\.[0-9]+)?)\s*ms$", re.IGNORECASE)


def parse_line(line):
    """Parse one [PerfCounters] line into {service: milliseconds}."""
    if not line.startswith(PREFIX):
        return None
    result = {}
    body = line[len(PREFIX):].strip(" |")
    for part in body.split("|"):
        part = part.strip()
        if not part:
            continue
        match = PAIR_RE.match(part)
        if match:
            name = match.group(1).strip()
            value = float(match.group(2))
            if name and value >= 0:
                result[name] = value
    return result or None


def load_log(path):
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_no, line in enumerate(handle, start=1):
            parsed = parse_line(line.strip())
            if parsed and "GameLoop" in parsed:
                parsed["Frame"] = len(rows) + 1
                parsed["SourceLine"] = line_no
                rows.append(parsed)
    if not rows:
        raise ValueError("No valid [PerfCounters] lines containing GameLoop were found.")
    df = pd.DataFrame(rows).set_index("Frame").fillna(0.0)
    df["FrameTime_ms"] = df["GameLoop"]
    return df


def analyse(df, target_fps):
    budget = 1000.0 / target_fps
    result = df.copy()
    result["InstantFPS"] = 1000.0 / result["FrameTime_ms"].clip(lower=0.001)
    result["Budget_ms"] = budget
    result["BudgetMiss"] = result["FrameTime_ms"] > budget

    # A stutter is a frame taking at least 1.5x the target frame budget.
    result["Stutter"] = result["FrameTime_ms"] > (1.5 * budget)

    def severity(ms):
        if ms <= budget:
            return "On target"
        if ms <= 1.5 * budget:
            return "Minor"
        if ms <= 2.5 * budget:
            return "Moderate"
        return "Severe"

    result["Severity"] = result["FrameTime_ms"].apply(severity)

    # 1% low FPS: average FPS of the slowest 1% of frames.
    slow_count = max(1, int(len(result) * 0.01 + 0.999999))
    slowest = result["FrameTime_ms"].nlargest(slow_count)
    one_percent_low = (1000.0 / slowest).mean()

    service_cols = [
        c for c in result.columns
        if c not in {
            "GameLoop", "FrameTime_ms", "InstantFPS", "Budget_ms",
            "BudgetMiss", "Stutter", "Severity", "SourceLine"
        }
    ]
    service_means = result[service_cols].mean().sort_values(ascending=False)
    return result, budget, one_percent_low, service_means


def recommendations(result, budget, service_means, target_fps):
    tips = []
    miss_rate = float(result["BudgetMiss"].mean() * 100)
    stutter_count = int(result["Stutter"].sum())

    if miss_rate > 20:
        tips.append(
            f"{miss_rate:.1f}% of frames exceed the {target_fps} FPS frame budget. "
            "Profile the busiest frames before optimising."
        )
    elif miss_rate > 0:
        tips.append(
            f"{miss_rate:.1f}% of frames miss the target frame budget. "
            "Inspect the frames marked as Minor, Moderate, or Severe."
        )
    else:
        tips.append("All recorded frames meet the selected target-FPS frame budget.")

    if stutter_count:
        tips.append(
            f"{stutter_count} stutter event(s) exceed 1.5x the frame budget "
            f"({1.5 * budget:.2f} ms). Inspect their top service contributors."
        )
    else:
        tips.append("No stutter events were detected using the 1.5x budget rule.")

    if not service_means.empty and service_means.iloc[0] > 0:
        name = str(service_means.index[0])
        tips.append(
            f"'{name}' has the highest average recorded service time "
            f"({service_means.iloc[0]:.2f} ms). Check whether it is a consistent bottleneck."
        )

    negative_unaccounted = result["GameLoop"] < 0
    if negative_unaccounted.any():
        tips.append("Some frame timing values are invalid or inconsistent; verify the source log.")
    return tips


def build_dashboard(result, budget, output_path, target_fps):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.index, y=result["FrameTime_ms"], mode="lines",
        name="Frame time", line=dict(width=1.5)
    ))
    stutters = result[result["Stutter"]]
    if not stutters.empty:
        fig.add_trace(go.Scatter(
            x=stutters.index, y=stutters["FrameTime_ms"],
            mode="markers", name="Stutter events",
            marker=dict(symbol="x", size=9)
        ))
    fig.add_hline(
        y=budget, line_dash="dash",
        annotation_text=f"{target_fps} FPS budget: {budget:.2f} ms"
    )
    fig.add_hline(
        y=1.5 * budget, line_dash="dot",
        annotation_text=f"Stutter threshold: {1.5 * budget:.2f} ms"
    )
    fig.update_layout(
        title="Game Performance Intelligence — Frame-Time Analysis",
        xaxis_title="Frame number",
        yaxis_title="Frame time (ms)",
        template="plotly_white",
        hovermode="x unified"
    )
    fig.write_html(str(output_path), include_plotlyjs="cdn")


def main():
    parser = argparse.ArgumentParser(
        description="Analyse game performance logs and detect frame-time stutters."
    )
    parser.add_argument("logfile", type=Path, help="Input log containing [PerfCounters] lines")
    parser.add_argument("--target-fps", type=float, default=60.0,
                        help="Target FPS used for frame-budget analysis (default: 60)")
    parser.add_argument("--export-dir", type=Path, default=Path("analysis_results"),
                        help="Directory for HTML, CSV and JSON outputs")
    args = parser.parse_args()

    if args.target_fps <= 0:
        parser.error("--target-fps must be greater than zero")
    if not args.logfile.is_file():
        parser.error(f"Log file not found: {args.logfile}")

    try:
        df = load_log(args.logfile)
        result, budget, one_percent_low, service_means = analyse(df, args.target_fps)
        tips = recommendations(result, budget, service_means, args.target_fps)

        args.export_dir.mkdir(parents=True, exist_ok=True)
        stem = args.logfile.stem
        csv_path = args.export_dir / f"{stem}_frame_diagnostics.csv"
        json_path = args.export_dir / f"{stem}_summary.json"
        html_path = args.export_dir / f"{stem}_dashboard.html"

        result.to_csv(csv_path, index_label="Frame")
        build_dashboard(result, budget, html_path, args.target_fps)

        summary = {
            "input_file": str(args.logfile),
            "frames_analysed": int(len(result)),
            "target_fps": args.target_fps,
            "frame_budget_ms": round(budget, 4),
            "average_fps": round(1000.0 / result["FrameTime_ms"].mean(), 2),
            "average_frame_time_ms": round(result["FrameTime_ms"].mean(), 3),
            "median_frame_time_ms": round(result["FrameTime_ms"].median(), 3),
            "p95_frame_time_ms": round(result["FrameTime_ms"].quantile(0.95), 3),
            "p99_frame_time_ms": round(result["FrameTime_ms"].quantile(0.99), 3),
            "one_percent_low_fps": round(float(one_percent_low), 2),
            "budget_miss_count": int(result["BudgetMiss"].sum()),
            "budget_miss_percent": round(float(result["BudgetMiss"].mean() * 100), 2),
            "stutter_count": int(result["Stutter"].sum()),
            "severity_counts": {
                str(k): int(v) for k, v in result["Severity"].value_counts().items()
            },
            "highest_average_service": (
                str(service_means.index[0]) if not service_means.empty else None
            ),
            "recommendations": tips,
        }
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("\n=== GAME PERFORMANCE INTELLIGENCE REPORT ===")
        print(f"Frames analysed       : {summary['frames_analysed']}")
        print(f"Target FPS            : {args.target_fps:g}")
        print(f"Average FPS           : {summary['average_fps']}")
        print(f"1% low FPS            : {summary['one_percent_low_fps']}")
        print(f"Average frame time    : {summary['average_frame_time_ms']} ms")
        print(f"P95 / P99 frame time  : {summary['p95_frame_time_ms']} / {summary['p99_frame_time_ms']} ms")
        print(f"Frames over budget    : {summary['budget_miss_count']} ({summary['budget_miss_percent']}%)")
        print(f"Stutter events        : {summary['stutter_count']}")
        print("\nRecommendations:")
        for i, tip in enumerate(tips, 1):
            print(f"{i}. {tip}")
        print("\nCreated:")
        print(f"- {html_path}")
        print(f"- {csv_path}")
        print(f"- {json_path}")
    except Exception as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
