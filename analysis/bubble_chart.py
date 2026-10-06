"""Bubble-chart comparing data volume across CNeuroMod datasets."""

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.transforms import offset_copy


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


EMOJI_FONT = Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
NEUTRAL = "#52514e"
BUBBLE_ALPHA = 0.75
EMOJI_PT = 36  # emoji height in the category label column


@lru_cache(maxsize=None)
def _emoji_image(char):
    """RGBA array of a color emoji rendered with Pillow, or None if the font is unavailable.

    matplotlib's Agg backend cannot draw color-bitmap fonts, so the glyph is
    rasterized separately and placed on the figure as an image.
    """
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(str(EMOJI_FONT), 109)  # the only size NotoColorEmoji ships
    except OSError:
        warnings.warn(f"Emoji font not found at {EMOJI_FONT}; category headers drawn without emoji")
        return None
    img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((10, 10), char, font=font, embedded_color=True)
    return np.asarray(img.crop(img.getbbox()))


def _label_color(color, alpha=BUBBLE_ALPHA, background="white"):
    """White text on a bubble, or black when the bubble (blended at `alpha` over `background`) is light.

    The 0.4 luminance cutoff keeps white on mid-tones, where black and white contrast about equally
    but white reads better on a saturated fill.
    """
    fg, bg = np.array(to_rgb(color)), np.array(to_rgb(background))
    rgb = alpha * fg + (1 - alpha) * bg
    lin = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "black" if lum > 0.4 else "white"


def _draw_group_column(ax, fig, groups, row_y, name_texts):
    """Tint each group's rows and label it vertically (emoji + name) left of the dataset names.

    The label column is offset in points from the left edge of the axes, past the widest
    dataset name, so it stays clear of the names whatever the column width.
    """
    renderer = fig.canvas.get_renderer()
    names_w = max(t.get_window_extent(renderer).width for t in name_texts) * 72 / fig.dpi
    bar_dx = -(names_w + 8)   # colored bar just left of the names
    label_dx = bar_dx - 12    # vertical label left of the bar

    for k, ((label, emoji, color, _), members) in enumerate(groups):
        y_top, y_bot = row_y[members[0]], row_y[members[-1]]
        y_mid = (y_top + y_bot) / 2
        ax.axhspan(y_bot - 0.5, y_top + 0.5, color=color, alpha=0.07, zorder=0, linewidth=0)
        if k:
            ax.axhline(y_top + 0.5, color="white", linewidth=2, zorder=1)

        ax.plot([-0.5, -0.5], [y_bot - 0.35, y_top + 0.35], color=color, linewidth=2.5,
                solid_capstyle="round", clip_on=False,
                transform=offset_copy(ax.transData, fig, x=bar_dx, units="points"))

        # Wrap long names onto two lines so they fit short groups.
        text = label.replace(" ", "\n", 1) if len(label) > 12 else label
        name = ax.text(-0.5, y_mid, text, rotation=90, ha="center", va="center",
                       fontsize=12, fontweight="bold", color=color, linespacing=1.0,
                       multialignment="center", clip_on=False,
                       transform=offset_copy(ax.transData, fig, x=label_dx, units="points"))
        # Upright emoji, vertically centered on the group, just left of the name.
        img = _emoji_image(emoji)
        if img is not None:
            ax.add_artist(AnnotationBbox(
                OffsetImage(img, zoom=EMOJI_PT / img.shape[0]), (0, 0.5), xycoords=name,
                xybox=(-4, 0), boxcoords="offset points", box_alignment=(1, 0.5),
                frameon=False, annotation_clip=False, zorder=4))


def make_bubble_chart(column_groups, pivot, datasets_list, title, out_path,
                      sort_by=None, row_colors=None, transpose=False, row_groups=None):
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
    row_groups    : optional list of (label, emoji, color, [datasets]) — rows are grouped
                    with the group's emoji and name written vertically in a left margin
                    column, bubbles take the group color and the column groups turn
                    neutral gray. Ignored when transpose is True.
    """
    if transpose:
        row_groups = None
    if row_groups:
        row_colors = {**{ds: color for _, _, color, members in row_groups for ds in members},
                      **(row_colors or {})}
        column_groups = [(g, NEUTRAL, fields) for g, _, fields in column_groups]

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

    # Non-transposed layout: datasets ordered group by group; `groups` keeps each
    # non-empty group with its member rows.
    groups = []
    if row_groups:
        for group in row_groups:
            members = [ds for ds in datasets_sorted if ds in group[3]]
            if members:
                groups.append((group, members))
        datasets_sorted = [ds for _, members in groups for ds in members]
    n_rows = len(datasets_sorted)

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
        LABEL_W = 3.2 + (0.6 if row_groups else 0)
        HEADER_H = 1.6

        fig, ax = plt.subplots(figsize=(LABEL_W + n_cols * COL_W, HEADER_H + n_rows * ROW_H))

        if row_groups:
            for c0 in [c0 for _, _, c0, _ in group_spans][1:]:
                ax.axvline(c0 - 0.5, color=NEUTRAL, linewidth=0.6, alpha=0.4, zorder=1)
        else:
            for gname, color, c0, c1 in group_spans:
                ax.axvspan(c0 - 0.5, c1 + 0.5, color=color, alpha=0.07, zorder=0)

        for gname, color, c0, c1 in group_spans:
            ax.text((c0 + c1) / 2, n_rows + 0.55, gname,
                    ha="center", va="center", fontsize=11, fontweight="bold", color=color)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels([c[0] for c in all_cols], rotation=45, ha="right", fontsize=11)
        for tick, (_, _, _, color) in zip(ax.get_xticklabels(), all_cols):
            tick.set_color(color)

        row_y = {ds: n_rows - 1 - i for i, ds in enumerate(datasets_sorted)}
        name_texts = []
        for ds_name in datasets_sorted:
            y = row_y[ds_name]
            name_color = row_colors.get(ds_name, "black") if row_groups else "black"
            name_texts.append(
                ax.text(-0.52, y, ds_name, ha="right", va="center", fontsize=11, color=name_color))
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
                ax.scatter(col_j, y, s=s, color=bubble_color, alpha=BUBBLE_ALPHA,
                           edgecolors=edge_color, linewidths=edge_width, zorder=3)
                if s <= MIN_S:
                    ax.text(col_j + 0.12, y, fmt(value, unit),
                            ha="left", va="center", fontsize=fs, fontweight="bold",
                            color="black", zorder=4)
                else:
                    text_color = _label_color(bubble_color) if row_groups else "white"
                    ax.text(col_j, y, fmt(value, unit),
                            ha="center", va="center", fontsize=fs, fontweight="bold",
                            color=text_color, zorder=4)

        if groups:
            _draw_group_column(ax, fig, groups, row_y, name_texts)

        ax.set_yticks([])
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(-0.55, n_rows + 1.0)
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
