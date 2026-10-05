"""Bubble-chart comparing data volume across CNeuroMod datasets."""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# Bubble area = UNIT_SCALES[unit] * log10(value + 1)
# Area scales with log so the full dynamic range of each unit fits in the bubble size range.
# MAX_S caps very large values; MIN_S sets the smallest visible dot.
UNIT_SCALES = {
    "h":     1000,
    "#img":  900,
    "#cond": 500,
    "#":     500,
}
MIN_S = 60
MAX_S = 6000


def value_to_size(value, unit):
    """Return (scatter_s, fontsize); area ∝ log10(value), clamped to [MIN_S, MAX_S]."""
    s = min(MAX_S, max(MIN_S, UNIT_SCALES[unit] * np.log10(value + 1)))
    if s < 300:
        fs = 5.5
    elif s < 800:
        fs = 7.0
    elif s < 2000:
        fs = 8.0
    else:
        fs = 9.0
    return s, fs


def fmt(value, unit):
    if unit in ("#img", "#cond", "#"):
        return f"{value / 1000:.1f}k" if value >= 1000 else str(int(value))
    if value >= 10:
        return f"{value:.0f}h"
    if value >= 1:
        return f"{value:.1f}h"
    return f"{value * 60:.0f}m"


def make_bubble_chart(column_groups, pivot, datasets_list, title, out_path,
                      sort_by=None, row_colors=None, transpose=False):
    """Draw and save a bubble chart.

    Parameters
    ----------
    column_groups : list of (group_name, color, [(label, dotpath, unit), ...])
    pivot         : DataFrame indexed by dataset name, columns are dotpaths
    datasets_list : list of dataset names to include
    title         : figure title string
    out_path      : Path to save the PNG
    sort_by       : dotpath to sort rows by (descending); defaults to first fMRI
                    per-subject column found, or alphabetical if none.
    row_colors    : optional dict {dataset_name: color} — overrides column-group
                    color for bubble fills (backgrounds and axis labels unchanged).
    transpose     : if True, datasets on x-axis and modalities on y-axis (landscape).
    """
    all_cols = []
    group_spans = []
    for group_name, color, fields in column_groups:
        start = len(all_cols)
        for label, path, unit in fields:
            all_cols.append((label, path, unit, color))
        group_spans.append((group_name, color, start, len(all_cols) - 1))
    n_cols = len(all_cols)

    neuro_hour_paths = [
        p for gname, _, fields in column_groups
        for _, p, u in fields
        if gname in ("Brain recordings", "Brain") and u == "h"
    ]

    def _neuro_sum(ds):
        total = 0.0
        for p in (neuro_hour_paths if sort_by is None else [sort_by]):
            if ds in pivot.index and p in pivot.columns:
                v = pivot.loc[ds, p]
                if pd.notna(v):
                    total += float(v)
        return total

    if sort_by is None or sort_by in pivot.columns:
        datasets_sorted = sorted(datasets_list, key=_neuro_sum, reverse=True)
    else:
        datasets_sorted = sorted(datasets_list)
    n_ds = len(datasets_sorted)

    col_maxima = {}
    for col_j, (label, path, unit, color) in enumerate(all_cols):
        if path not in pivot.columns:
            continue
        col_vals = pivot.loc[pivot.index.isin(datasets_sorted), path].dropna()
        col_vals = col_vals[col_vals > 0]
        if not col_vals.empty:
            col_maxima[col_j] = col_vals.idxmax()

    if not transpose:
        COL_W, ROW_H = 0.90, 0.65
        LABEL_W = 3.2
        HEADER_H = 1.6

        fig, ax = plt.subplots(figsize=(LABEL_W + n_cols * COL_W, HEADER_H + n_ds * ROW_H))

        for gname, color, c0, c1 in group_spans:
            ax.axvspan(c0 - 0.5, c1 + 0.5, color=color, alpha=0.07, zorder=0)

        for gname, color, c0, c1 in group_spans:
            ax.text((c0 + c1) / 2, n_ds + 0.55, gname,
                    ha="center", va="center", fontsize=11, fontweight="bold", color=color)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels([c[0] for c in all_cols], rotation=45, ha="right", fontsize=11)
        for tick, (_, _, _, color) in zip(ax.get_xticklabels(), all_cols):
            tick.set_color(color)

        for row_i, ds_name in enumerate(datasets_sorted):
            y = n_ds - 1 - row_i
            ax.text(-0.52, y, ds_name, ha="right", va="center", fontsize=11)
            for col_j, (label, path, unit, color) in enumerate(all_cols):
                if path not in pivot.columns or ds_name not in pivot.index:
                    continue
                value = pivot.loc[ds_name, path]
                if pd.isna(value) or value == 0:
                    continue
                s, fs = value_to_size(value, unit)
                bubble_color = row_colors.get(ds_name, color) if row_colors else color
                is_col_max = col_maxima.get(col_j) == ds_name
                edge_color = "black" if is_col_max else "none"
                edge_width = 2.5 if is_col_max else 0
                ax.scatter(col_j, y, s=s, color=bubble_color, alpha=0.75,
                           edgecolors=edge_color, linewidths=edge_width, zorder=3)
                if s <= MIN_S:
                    ax.text(col_j + 0.12, y, fmt(value, unit),
                            ha="left", va="center", fontsize=fs, fontweight="bold",
                            color="black", zorder=4)
                else:
                    ax.text(col_j, y, fmt(value, unit),
                            ha="center", va="center", fontsize=fs, fontweight="bold",
                            color="white", zorder=4)

        ax.set_yticks([])
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(-0.55, n_ds + 1.0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis="x", linestyle=":", alpha=0.35, zorder=1)

    else:
        # Landscape: datasets on x-axis, modalities on y-axis.
        COL_W, ROW_H = 0.90, 0.65
        MOD_LABEL_W = 1.5
        HEADER_H = 1.6

        fig, ax = plt.subplots(figsize=(MOD_LABEL_W + n_ds * COL_W, HEADER_H + n_cols * ROW_H))

        for gname, color, c0, c1 in group_spans:
            ax.axhspan(c0 - 0.5, c1 + 0.5, color=color, alpha=0.07, zorder=0)

        for gname, color, c0, c1 in group_spans:
            ax.text(n_ds + 0.55, (c0 + c1) / 2, gname,
                    ha="center", va="center", fontsize=11, fontweight="bold", color=color,
                    rotation=90)

        ax.set_xticks(range(n_ds))
        ax.set_xticklabels(datasets_sorted, rotation=45, ha="right", fontsize=11)
        if row_colors:
            for tick, ds in zip(ax.get_xticklabels(), datasets_sorted):
                tick.set_color(row_colors.get(ds, "black"))

        ax.set_yticks(range(n_cols))
        ax.set_yticklabels([c[0] for c in all_cols], fontsize=11)
        for tick, (_, _, _, color) in zip(ax.get_yticklabels(), all_cols):
            tick.set_color(color)

        for row_i, ds_name in enumerate(datasets_sorted):
            for col_j, (label, path, unit, color) in enumerate(all_cols):
                if path not in pivot.columns or ds_name not in pivot.index:
                    continue
                value = pivot.loc[ds_name, path]
                if pd.isna(value) or value == 0:
                    continue
                s, fs = value_to_size(value, unit)
                bubble_color = row_colors.get(ds_name, color) if row_colors else color
                is_col_max = col_maxima.get(col_j) == ds_name
                edge_color = "black" if is_col_max else "none"
                edge_width = 2.5 if is_col_max else 0
                ax.scatter(row_i, col_j, s=s, color=bubble_color, alpha=0.75,
                           edgecolors=edge_color, linewidths=edge_width, zorder=3)
                if s <= MIN_S:
                    ax.text(row_i + 0.12, col_j, fmt(value, unit),
                            ha="left", va="center", fontsize=fs, fontweight="bold",
                            color="black", zorder=4)
                else:
                    ax.text(row_i, col_j, fmt(value, unit),
                            ha="center", va="center", fontsize=fs, fontweight="bold",
                            color="white", zorder=4)

        ax.set_xlim(-0.5, n_ds + 1.0)
        ax.set_ylim(-0.55, n_cols - 0.5)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis="y", linestyle=":", alpha=0.35, zorder=1)

    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"Saved {out_path.name}")
