# Patches for sibling repositories

Standalone diffs of changes that other Atomize variants should receive
unchanged. Apply from the sibling's root:

```bash
git apply --3way docs/automation/patches/<name>.patch   # or: patch -p1 < <name>.patch
```

- `2026-09-18_main_window_idle_plot_marks.patch` — `atomize/main/main_window.py`
  only: `IDLE_PLOT_S = 10`, a grey dot icon for a plot whose source is still
  connected but silent for 10 s, one 2 s `QTimer` in `NameList`, tooltip
  "Source connected, idle since HH:MM:SS". Verified offscreen on 2026-09-18.
