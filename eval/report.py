"""Run evaluation cases under knob variants and report metrics / A-B diffs.

This actually converts the sample PDFs (docling, ML models), so it is meant to
be run **manually**, not in the default test suite:

    python -m eval.report                                  # all cases, baseline
    python -m eval.report --variants baseline,force_ocr    # two variants
    python -m eval.report --compare baseline force_ocr     # show the delta

The A/B view answers "did this knob actually help?" by scoring the same sample
under different :data:`VARIANTS` and printing ``other - base`` per metric.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from app.models import ConversionOptions

from eval.cases import CASES, CASES_BY_NAME, EvalCase

# Named knob overrides applied on top of each case's base options.  Add entries
# here to A/B new settings — the runner needs no other change.
VARIANTS: dict[str, Callable[[ConversionOptions], ConversionOptions]] = {
    "baseline": lambda o: o,
    "no_cell_match": lambda o: o.model_copy(update={"do_cell_matching": False}),
    "high_res": lambda o: o.model_copy(update={"image_scale": 4.0}),
    "force_ocr": lambda o: o.model_copy(update={"force_full_page_ocr": True}),
    "low_conf": lambda o: o.model_copy(update={"ocr_confidence_threshold": 0.1}),
    "preprocess": lambda o: o.model_copy(update={"ocr_preprocess": True}),
    "pp_low_conf": lambda o: o.model_copy(update={
        "ocr_preprocess": True, "ocr_confidence_threshold": 0.1}),
}


@dataclass
class CaseResult:
    case: str
    variant: str
    scores: dict[str, float]


def _apply_variant(case: EvalCase, variant: str) -> ConversionOptions:
    if variant not in VARIANTS:
        raise KeyError(f"unknown variant {variant!r}; known: {sorted(VARIANTS)}")
    return VARIANTS[variant](case.base_options())


def run(
    cases: list[EvalCase] | None = None,
    variants: list[str] | None = None,
) -> list[CaseResult]:
    """Convert each *case* under each *variant* and score the output.

    ``app.converter.convert`` is imported lazily so importing this module stays
    cheap (and docling-free) for callers that only need :data:`VARIANTS`.
    """
    from app.converter import convert

    cases = cases if cases is not None else CASES
    variants = variants if variants is not None else ["baseline"]
    results: list[CaseResult] = []
    for case in cases:
        for variant in variants:
            opts = _apply_variant(case, variant)
            content = convert(case.sample, opts).content
            results.append(CaseResult(case.name, variant, case.score(content)))
    return results


def _metric_names(results: list[CaseResult]) -> list[str]:
    names: list[str] = []
    for r in results:
        for k in r.scores:
            if k not in names:
                names.append(k)
    return names


def format_table(results: list[CaseResult]) -> str:
    """Render results as a ``case | variant | metric...`` text table."""
    metrics = _metric_names(results)
    header = ["case", "variant", *metrics]
    rows = [header]
    for r in results:
        rows.append([
            r.case,
            r.variant,
            *[f"{r.scores.get(m, float('nan')):.3f}" for m in metrics],
        ])
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        for row in rows
    )


def format_compare(results: list[CaseResult], base: str, other: str) -> str:
    """Render ``other - base`` deltas per case and metric."""
    by_key = {(r.case, r.variant): r.scores for r in results}
    cases = [c for c in dict.fromkeys(r.case for r in results)]
    metrics: list[str] = _metric_names(results)
    header = ["case", *[f"Δ{m}" for m in metrics]]
    rows = [header]
    for case in cases:
        b = by_key.get((case, base), {})
        o = by_key.get((case, other), {})
        cells = [case]
        for m in metrics:
            if m in b and m in o:
                cells.append(f"{o[m] - b[m]:+.3f}")
            else:
                cells.append("-")
        rows.append(cells)
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    out = [f"A/B: {other} - {base}"]
    out += [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        for row in rows
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PDFto conversion quality report")
    parser.add_argument(
        "--variants", default="baseline",
        help=f"comma-separated variants (known: {','.join(VARIANTS)})")
    parser.add_argument(
        "--cases", default="",
        help="comma-separated case names (default: all)")
    parser.add_argument(
        "--include-external", action="store_true",
        help="also include fetched real-world cases (eval.external_cases)")
    parser.add_argument(
        "--compare", nargs=2, metavar=("BASE", "OTHER"),
        help="also print the per-metric delta between two variants")
    args = parser.parse_args(argv)

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    if args.compare:
        for v in args.compare:
            if v not in variants:
                variants.append(v)
    available = dict(CASES_BY_NAME)
    default_cases = list(CASES)
    if args.include_external:
        from eval.external_cases import external_cases

        ext = external_cases()
        if not ext:
            print("note: no external samples found; run "
                  "scripts/fetch_external_samples.py first")
        default_cases += ext
        available.update({c.name: c for c in ext})

    if args.cases:
        cases = [available[n.strip()] for n in args.cases.split(",") if n.strip()]
    else:
        cases = default_cases

    results = run(cases, variants)
    print(format_table(results))
    if args.compare:
        print()
        print(format_compare(results, args.compare[0], args.compare[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
