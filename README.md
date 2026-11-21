# Game Performance Intelligence & Stutter Detection System

An extended learning project based on the public repository [bm01/PerfAnalyzer](https://github.com/bm01/PerfAnalyzer).

This version keeps the original `[PerfCounters]` log style and adds:
- target-FPS frame-budget analysis (for example, 60 FPS = 16.67 ms/frame)
- 1% low FPS
- Minor / Moderate / Severe frame-time classifications
- stutter detection at 1.5x the selected frame budget
- per-frame diagnostic CSV and machine-readable JSON summary
- interactive Plotly HTML dashboard
- rule-based performance recommendations

## Attribution

The original repository is by `bm01`: https://github.com/bm01/PerfAnalyzer  
The original repository is published under Apache License 2.0. This derivative learning project should retain the original copyright and license notice when you combine it with the upstream source. This folder contains a new standalone implementation of the documented log format; review the upstream license before redistributing a merged fork.

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python game_performance_intelligence.py samples/sample_perf.log --target-fps 60
```

Choose another target:

```bash
python game_performance_intelligence.py samples/sample_perf.log --target-fps 120 --export-dir results_120fps
```

Outputs:
- `*_dashboard.html`: interactive frame-time chart
- `*_frame_diagnostics.csv`: per-frame values and severity labels
- `*_summary.json`: summary metrics and recommendations

## Important metric definitions

- Frame budget = `1000 / target_fps` milliseconds.
- A budget miss is a frame slower than the target frame budget.
- A stutter event is defined here as a frame taking more than `1.5 × frame budget`. This is a project-defined heuristic, not a universal industry standard.
- 1% low FPS is calculated as the mean instantaneous FPS of the slowest 1% of frames. With very short captures, at least one frame is used.

## Next development steps

1. Validate results using real game-engine or capture-tool logs.
2. Add automated tests for malformed, missing, and extreme counter values.
3. Compare results against PresentMon or another trusted frame-capture tool.
4. Add hardware telemetry only after verifying that the selected data source is available and reliable.

Do not claim measured performance gains unless you have collected repeatable benchmark data on real hardware.
