"""Render the Italian PII benchmark summary as Markdown tables and static SVG charts.

Why: reviewers need the numbers (with CIs) and a few honest pictures without installing a
plotting stack; stdlib-only SVG keeps the CI job and reproduction dependency-free.
What: reads <results>/summary.json, writes <results>/tables.md and <results>/charts/*.svg;
for the full run (results/) it also refreshes the block between the result markers in README.md.
Test: `python3 report.py --results results-subset` writes tables.md + 3 SVGs; the unit test
renders a synthetic summary and checks every system appears in the table and the charts.
"""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = HERE / "README.md"
MARK_START, MARK_END = "<!-- results:start -->", "<!-- results:end -->"
KEY = ["pseudora_generic_professional", "pseudora_matched", "ablation_regex_presidio",
       "presidio_vanilla_it", "rizzo_pii_only"]
KEY_TYPES = ["PERSON", "FISCAL_CODE", "ADDRESS", "EMAIL", "PHONE", "DATE_OF_BIRTH", "IBAN", "ID_DOCUMENT",
             "LICENSE_PLATE", "USERNAME", "IP_ADDRESS", "SOCIAL_SECURITY", "VAT_NUMBER", "CREDIT_CARD", "EMPLOYEE_ID"]
# Validated (dataviz validator, --pairs all, light): slots 1-3 of the reference palette.
# Aqua is < 3:1 on the surface, so every mark is also direct-labelled or shape-encoded.
FAMILY = {"pseudora": ("Pseudora presets", "#2a78d6", "circle"),
          "ablation": ("Pseudora ablations", "#1baf7a", "square"),
          "external": ("Other tools", "#eb6834", "triangle")}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Hand-placed direct labels for the scatter (dx, dy, anchor); the rest are in the tooltip and tables.
LABELS = {"presidio_vanilla_it": (9, 4, "start"), "rizzo_pii_only": (9, 4, "start"), "rizzo_default": (9, 4, "start"),
          "ablation_regex_presidio": (0, -10, "middle"), "ablation_regex": (12, 4, "start")}
# Labels parked in empty space with a leader line, as (leak, fp) data coordinates.
PARKED = {"pseudora_generic_professional": (0.01, 0.045)}
FONT = 'font-family="system-ui, -apple-system, Segoe UI, sans-serif"'


def family(name: str) -> str:
    """Why: colour/shape must follow the system's family, never its rank.
    What: maps a system id to pseudora / ablation / external.
    Test: family('ablation_regex') == 'ablation'; family('rizzo_default') == 'external'."""
    return "ablation" if name.startswith("ablation_") else "pseudora" if name.startswith("pseudora_") else "external"


def pct(x: float) -> str:
    return f"{100 * x:.1f}"


def ci(c: list[float]) -> str:
    return f"[{pct(c[0])}, {pct(c[1])}]"


def tables(summary: dict) -> str:
    """Why: the README must carry the exact numbers the charts draw.
    What: Markdown tables (headline with CIs, deltas, per type, per genre, negatives, hard cases).
    Test: every system id in summary['systems'] appears in the headline table."""
    S = summary["systems"]
    order = sorted(S, key=lambda n: -S[n]["overall"]["lenient_f1"])
    key = [k for k in KEY if k in S] or list(S)
    out = [f"Dataset `{summary['dataset']}` · {summary['documents']} documents · bootstrap {summary['bootstrap_samples']}"
           " resamples over documents · all values in %.\n",
           "### Overall\n",
           "| System | Strict F1 [95% CI] | Lenient P | Lenient R | Lenient F1 [95% CI] | Leak rate [95% CI] | FP on negatives [95% CI] | ms / 1k chars |",
           "|---|---|---|---|---|---|---|---|"]
    for n in order:
        o, c = S[n]["overall"], S[n]["ci95"]
        out.append(f"| `{n}` | {pct(o['strict_f1'])} {ci(c['strict_f1'])} | {pct(o['lenient_p'])} | {pct(o['lenient_r'])} | "
                   f"**{pct(o['lenient_f1'])}** {ci(c['lenient_f1'])} | {pct(o['leak_rate'])} {ci(c['leak_rate'])} | "
                   f"{pct(o['neg_fp_rate'])} {ci(c['neg_fp_rate'])} | {S[n]['meta'].get('ms_per_1k_chars', '–')} |")
    ref = summary.get("reference")
    out += ["", f"### Difference vs `{ref}` (paired bootstrap, 95% CI; positive leak delta = leaks more)\n",
            "| System | Δ strict F1 | Δ lenient F1 | Δ leak rate |", "|---|---|---|---|"]
    for n in order:
        d = S[n]["ci95"].get("delta_vs_reference")
        if n != ref and d:
            out.append(f"| `{n}` | {ci(d['strict_f1'])} | {ci(d['lenient_f1'])} | {ci(d['leak_rate'])} |")
    out += ["", "### Lenient recall by entity type (leak rate in parentheses)\n",
            "| Type (gold spans) | " + " | ".join(f"`{k}`" for k in key) + " |", "|---" * (len(key) + 1) + "|"]
    for t in sorted(S[key[0]]["per_type"], key=lambda t: -S[key[0]]["per_type"][t]["gold"]):
        cells = [f"{pct(S[k]['per_type'][t]['lenient_recall'])} ({pct(S[k]['per_type'][t]['leak_rate'])})" for k in key]
        out.append(f"| {t} ({S[key[0]]['per_type'][t]['gold']}) | " + " | ".join(cells) + " |")
    out += ["", "### Lenient F1 by genre (FP rate on negative look-alikes in parentheses)\n",
            "| Genre | " + " | ".join(f"`{k}`" for k in key) + " |", "|---" * (len(key) + 1) + "|"]
    for g in S[key[0]]["per_genre"]:
        cells = [(f"– ({pct(S[k]['per_genre'][g]['neg_fp_rate'])})" if g == "negative" else
                  f"{pct(S[k]['per_genre'][g]['lenient_f1'])} ({pct(S[k]['per_genre'][g]['neg_fp_rate'])})") for k in key]
        out.append(f"| {g} | " + " | ".join(cells) + " |")
    out += ["", "### Negative look-alikes wrongly masked (lower is better)\n",
            "| Look-alike (spans) | " + " | ".join(f"`{k}`" for k in key) + " |", "|---" * (len(key) + 1) + "|"]
    for t, v in S[key[0]]["negatives"].items():
        out.append(f"| {t} ({v['spans']}) | " + " | ".join(pct(S[k]["negatives"][t]["masked_rate"]) for k in key) + " |")
    out.append(f"\nDocuments with no PII at all that got at least one mask: "
               + ", ".join(f"`{k}` {pct(S[k]['negative_docs_flagged_rate'])}" for k in key) + ".")
    out += ["", "### Hard cases (lenient recall)\n",
            "| Hard case (spans) | " + " | ".join(f"`{k}`" for k in key) + " |", "|---" * (len(key) + 1) + "|"]
    for h, v in sorted(S[key[0]]["hard_cases"].items(), key=lambda kv: -kv[1]["spans"]):
        out.append(f"| {h} ({v['spans']}) | " + " | ".join(pct(S[k]["hard_cases"][h]["lenient_recall"]) for k in key) + " |")
    return "\n".join(out) + "\n"


def svg(w: int, h: int, title: str, desc: str, body: list[str]) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-labelledby="t d" {FONT}><title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>'
            f'<rect width="{w}" height="{h}" fill="{SURFACE}"/>' + "".join(body) + "</svg>\n")


def marker(shape: str, x: float, y: float, color: str, tip: str, r: float = 5) -> str:
    t = f"<title>{escape(tip)}</title>"
    ring = f'stroke="{SURFACE}" stroke-width="2"'
    if shape == "square":
        return f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" rx="1.5" fill="{color}" {ring}>{t}</rect>'
    if shape == "triangle":
        return (f'<path d="M{x:.1f},{y - r * 1.2:.1f} L{x + r * 1.1:.1f},{y + r * 0.8:.1f} L{x - r * 1.1:.1f},{y + r * 0.8:.1f} Z" '
                f'fill="{color}" {ring}>{t}</path>')
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" {ring}>{t}</circle>'


def legend(x: float, y: float) -> list[str]:
    out = []
    for i, (label, color, shape) in enumerate(FAMILY.values()):
        out += [marker(shape, x + i * 170, y, color, label), f'<text x="{x + i * 170 + 12}" y="{y + 4}" font-size="12" fill="{INK2}">{label}</text>']
    return out


def chart_f1(S: dict, corpus: str = "it_pii_v1, 750") -> str:
    """Why: the headline comparison, with uncertainty visible rather than implied.
    What: one horizontal bar per system (lenient F1) + 95% CI whisker + direct value label."""
    order = sorted(S, key=lambda n: -S[n]["overall"]["lenient_f1"])
    L, W, row, top = 250, 420, 22, 64
    h = top + row * len(order) + 40
    x = lambda v: L + v * W  # noqa: E731
    b = [f'<text x="16" y="24" font-size="15" font-weight="600" fill="{INK}">Lenient F1 by system (95% bootstrap CI)</text>',
         f'<text x="16" y="42" font-size="12" fill="{INK2}">Italian PII benchmark {corpus} synthetic documents. Higher is better.</text>']
    b += legend(L, h - 14)
    for v in (0, .2, .4, .6, .8, 1):
        b += [f'<line x1="{x(v)}" y1="{top - 6}" x2="{x(v)}" y2="{top + row * len(order)}" stroke="{GRID}" stroke-width="1"/>',
              f'<text x="{x(v)}" y="{top + row * len(order) + 14}" font-size="11" fill="{MUTED}" text-anchor="middle">{int(v * 100)}</text>']
    for i, n in enumerate(order):
        o, c, (label, color, _) = S[n]["overall"], S[n]["ci95"]["lenient_f1"], FAMILY[family(n)]
        y = top + i * row
        tip = f"{n}: lenient F1 {pct(o['lenient_f1'])}% (CI {pct(c[0])}–{pct(c[1])}), {label}"
        b += [f'<text x="{L - 8}" y="{y + 13}" font-size="12" fill="{INK}" text-anchor="end">{escape(n)}</text>',
              f'<rect x="{L}" y="{y + 4}" width="{max(o["lenient_f1"] * W, 1):.1f}" height="{row - 8}" rx="4" fill="{color}"><title>{escape(tip)}</title></rect>',
              f'<rect x="{L}" y="{y + 4}" width="4" height="{row - 8}" fill="{color}"/>',  # square baseline end
              f'<line x1="{x(c[0]):.1f}" y1="{y + row / 2}" x2="{x(c[1]):.1f}" y2="{y + row / 2}" stroke="{INK}" stroke-width="1.5"/>',
              f'<text x="{x(c[1]) + 6:.1f}" y="{y + 15}" font-size="11" fill="{INK2}">{pct(o["lenient_f1"])}</text>']
    b.append(f'<line x1="{L}" y1="{top - 6}" x2="{L}" y2="{top + row * len(order)}" stroke="{AXIS}" stroke-width="1"/>')
    return svg(L + W + 70, h, "Lenient F1 by system", "Bar chart of lenient F1 with 95% CIs for every benchmarked system; "
               "values are in tables.md.", b)


def chart_tradeoff(S: dict) -> str:
    """Why: recall-heavy tools leak less but mask look-alikes; one number hides that trade.
    What: scatter of leak rate (x) vs FP rate on negative look-alikes (y); colour + shape by family."""
    L, T, W, H = 64, 60, 560, 380
    sx = lambda v: L + v * W  # noqa: E731
    sy = lambda v: T + H - v * H  # noqa: E731
    b = [f'<text x="16" y="24" font-size="15" font-weight="600" fill="{INK}">Leak rate vs false masking on negative look-alikes</text>',
         f'<text x="16" y="42" font-size="12" fill="{INK2}">Both lower is better: bottom-left corner wins. Hover a mark for its name.</text>']
    for v in (0, .2, .4, .6, .8, 1):
        b += [f'<line x1="{sx(v)}" y1="{T}" x2="{sx(v)}" y2="{T + H}" stroke="{GRID}"/>',
              f'<line x1="{L}" y1="{sy(v)}" x2="{L + W}" y2="{sy(v)}" stroke="{GRID}"/>',
              f'<text x="{sx(v)}" y="{T + H + 16}" font-size="11" fill="{MUTED}" text-anchor="middle">{int(v * 100)}%</text>',
              f'<text x="{L - 6}" y="{sy(v) + 4}" font-size="11" fill="{MUTED}" text-anchor="end">{int(v * 100)}%</text>']
    b += [f'<text x="{L + W / 2}" y="{T + H + 36}" font-size="12" fill="{INK2}" text-anchor="middle">Leak rate (gold PII tokens left unmasked)</text>',
          f'<text x="16" y="{T + H / 2}" font-size="12" fill="{INK2}" text-anchor="middle" transform="rotate(-90 16 {T + H / 2})">FP rate on negatives</text>',
          f'<line x1="{L}" y1="{T + H}" x2="{L + W}" y2="{T + H}" stroke="{AXIS}"/>']
    b += legend(L, T + H + 60)
    for n in sorted(S, key=lambda n: family(n) == "pseudora"):
        o, (label, color, shape) = S[n]["overall"], FAMILY[family(n)]
        x, y = sx(o["leak_rate"]), sy(o["neg_fp_rate"])
        b.append(marker(shape, x, y, color, f"{n}: leak {pct(o['leak_rate'])}%, FP on negatives {pct(o['neg_fp_rate'])}% ({label})"))
        if n in PARKED:
            lx, ly = sx(PARKED[n][0]), sy(PARKED[n][1])
            b += [f'<line x1="{x:.1f}" y1="{y + 5:.1f}" x2="{lx + 60:.1f}" y2="{ly - 10:.1f}" stroke="{MUTED}" stroke-width="1"/>',
                  f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="11" fill="{INK}">{escape(n)}</text>']
        if n in LABELS:
            dx, dy, anchor = LABELS[n]
            b.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" font-size="11" fill="{INK}" text-anchor="{anchor}">{escape(n)}</text>')
    return svg(L + W + 40, T + H + 80, "Leak rate vs false masking", "Scatter: leak rate against FP rate on negatives per system.", b)


def chart_types(S: dict) -> str:
    """Why: averages hide which entity types each system misses.
    What: heatmap of lenient recall, entity type x key system, sequential blue, value in every cell."""
    key = [k for k in KEY if k in S] or list(S)
    types = [t for t in KEY_TYPES if t in S[key[0]]["per_type"]]
    L, T, cw, ch = 150, 150, 104, 24
    b = [f'<text x="16" y="24" font-size="15" font-weight="600" fill="{INK}">Lenient recall by entity type</text>',
         f'<text x="16" y="42" font-size="12" fill="{INK2}">Share of gold spans touched by a compatible prediction. Darker = higher.</text>']
    for j, k in enumerate(key):
        b.append(f'<text x="{L + j * cw + 12}" y="{T - 8}" font-size="11" fill="{INK}" text-anchor="start" '
                 f'transform="rotate(-30 {L + j * cw + 12} {T - 8})">{escape(k)}</text>')
    for i, t in enumerate(types):
        y = T + i * ch
        b.append(f'<text x="{L - 8}" y="{y + 16}" font-size="12" fill="{INK}" text-anchor="end">{t}</text>')
        for j, k in enumerate(key):
            v = S[k]["per_type"][t]["lenient_recall"]
            step = min(int(v * len(SEQ)), len(SEQ) - 1)
            ink = "#ffffff" if step >= 3 else INK
            b += [f'<rect x="{L + j * cw + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="3" fill="{SEQ[step]}">'
                  f'<title>{escape(f"{k} · {t}: {pct(v)}%")}</title></rect>',
                  f'<text x="{L + j * cw + cw / 2}" y="{y + 16}" font-size="11" fill="{ink}" text-anchor="middle">{pct(v)}</text>']
    return svg(L + cw * len(key) + 150, T + ch * len(types) + 20, "Lenient recall by entity type",
               "Heatmap of lenient recall per entity type for the five key systems; values printed in each cell.", b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=HERE / "results")
    args = ap.parse_args()
    summary = json.loads((args.results / "summary.json").read_text())
    md = tables(summary)
    (args.results / "tables.md").write_text(md)
    charts = args.results / "charts"
    charts.mkdir(exist_ok=True)
    corpus = f"{Path(summary['dataset']).stem}, {summary['documents']}"
    for name, fn in (("f1_ci", lambda S: chart_f1(S, corpus)), ("leak_vs_fp", chart_tradeoff), ("recall_by_type", chart_types)):
        (charts / f"{name}.svg").write_text(fn(summary["systems"]))
    if args.results.resolve() == (HERE / "results").resolve() and README.exists():
        text = README.read_text()
        if MARK_START in text and MARK_END in text:
            head, rest = text.split(MARK_START, 1)
            README.write_text(head + MARK_START + "\n" + md + MARK_END + rest.split(MARK_END, 1)[1])
    print(f"wrote {args.results / 'tables.md'} and {charts}/*.svg")


if __name__ == "__main__":
    main()
