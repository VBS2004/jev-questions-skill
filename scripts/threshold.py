#!/usr/bin/env python3
"""Calibrate a threshold on the hard slice (SKILL.md §7). stdlib only, no API.

    python scripts/threshold.py SCORES.jsonl --positive "whole;middle" --hard middle
                               [--negative content] [--direction high] [--max-false 0]
                               [--grid 0.2:0.8:0.05] [--json]

A check for sponsor reads caught 94% of whole reads at 0.5 and 50% of the same reads'
middle 30 seconds, which is the shape real edits produce. The whole example is the easy
case and passes at almost any threshold. So split your known violations into groups, mark
the hardest, and read the threshold off the two things that bound it: where genuine content
*peaks*, and where the hardest violations *sit*.

Input, one JSON object per line: {"id": ..., "group": "whole", "score": 0.31}
  --positive  groups the question must catch (repeat the flag, or separate with ";")
  --hard      the subset of those that are hard (the shape you will actually see)
  --negative  groups that are genuine and must not fire (default: every other group)
  --direction high (fires when score >= t; default) or low (fires when score <= t)

Prints per-group ranges, then recall and false fires at each threshold, and a suggestion:
the threshold with the best recall on the hard slice among those flagging at most
--max-false genuine items. That is read from one sample, not an optimiser: check it on
items you held out, and re-do it when the wording changes.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict


def fires(score: float, t: float, direction: str) -> bool:
    return score >= t if direction == "high" else score <= t


def parse_grid(spec: str) -> list[float]:
    lo, hi, step = (float(x) for x in spec.split(":"))
    out, x = [], lo
    while x <= hi + 1e-9:
        out.append(round(x, 6))
        x += step
    return out


def analyse(groups: dict[str, list[tuple[str, float]]], positive: list[str], hard: list[str],
            negative: list[str], direction: str, grid: list[float], max_false: int) -> dict:
    def rate(names: list[str], t: float) -> tuple[int, int]:
        items = [s for g in names for _, s in groups.get(g, [])]
        return sum(fires(s, t, direction) for s in items), len(items)

    pos_items = [s for g in positive for _, s in groups.get(g, [])]
    hard_items = [s for g in hard for _, s in groups.get(g, [])]
    neg_items = [(i, s) for g in negative for i, s in groups.get(g, [])]
    if not pos_items or not neg_items:
        raise SystemExit("need at least one positive and one negative item")

    # Candidate thresholds: the grid, plus every score (any other threshold is equivalent).
    sweep = []
    for t in grid:
        row = {"t": t}
        for g in positive:
            k, n = rate([g], t)
            row[g] = k / n if n else None
        k, n = rate(negative, t)
        row["false"], row["n_neg"] = k, n
        sweep.append(row)

    cands = sorted({s for s in pos_items + [s for _, s in neg_items]})
    best = None
    for t in cands:
        false = sum(fires(s, t, direction) for _, s in neg_items)
        if false > max_false:
            continue
        target = hard_items or pos_items
        recall = sum(fires(s, t, direction) for s in target) / len(target)
        # prefer more recall, then the threshold furthest from the genuine peak
        key = (recall, -abs(t - (max(s for _, s in neg_items) if direction == "high"
                                  else min(s for _, s in neg_items))))
        if best is None or key > best[0]:
            best = (key, t, recall, false)
    stats = {}
    for g, items in groups.items():
        v = [s for _, s in items]
        stats[g] = {"n": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)}
    return {"stats": stats, "sweep": sweep,
            "suggestion": None if best is None else
            {"threshold": best[1], "recall_target": best[2], "false_fires": best[3]},
            "genuine_peak": max(s for _, s in neg_items) if direction == "high"
            else min(s for _, s in neg_items),
            "overlap": {
                "hardest_violations": sorted(hard_items or pos_items,
                                             reverse=direction == "low")[:6],
                "highest_genuine": sorted((s for _, s in neg_items),
                                          reverse=direction == "high")[:6],
            },
            "neg_items": neg_items}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--positive", action="append", required=True)
    ap.add_argument("--hard", action="append", default=[])
    ap.add_argument("--negative", action="append", default=[])
    ap.add_argument("--direction", choices=("high", "low"), default="high")
    ap.add_argument("--max-false", type=int, default=0)
    ap.add_argument("--grid", default="0.2:0.8:0.05")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    fh = sys.stdin if a.file == "-" else open(a.file)
    with fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                groups[r["group"]].append((str(r.get("id", "")), float(r["score"])))
    def names(values: list[str]) -> list[str]:
        return [g.strip() for v in values for g in v.split(";") if g.strip()]

    positive, hard, negative = names(a.positive), names(a.hard), names(a.negative)
    negative = negative or [g for g in groups if g not in positive]
    for g in positive + hard + negative:
        if g not in groups:
            raise SystemExit(f"no group named {g!r}; have {sorted(groups)}")

    res = analyse(groups, positive, hard, negative, a.direction, parse_grid(a.grid), a.max_false)
    if a.json:
        res.pop("neg_items")
        json.dump(res, sys.stdout, indent=1)
        print()
        return 0

    print(f"{'group':24} {'n':>5} {'min':>6} {'median':>7} {'max':>6}")
    for g, s in res["stats"].items():
        role = "+" if g in positive else "-" if g in negative else " "
        mark = "  <- hard" if g in hard else ""
        print(f"{role} {g[:22]:22} {s['n']:5d} {s['min']:6.2f} {s['median']:7.2f} "
              f"{s['max']:6.2f}{mark}")
    peak_word = "peaks" if a.direction == "high" else "bottoms out"
    print(f"\ngenuine content {peak_word} at {res['genuine_peak']:.2f}")
    ov = res["overlap"]
    fmt = " ".join(f"{x:.2f}" for x in ov["hardest_violations"])
    print(f"hardest to catch ({'hard slice' if hard else 'positives'}):  {fmt}")
    print("genuine content, closest to firing:  " + " ".join(f"{x:.2f}" for x in ov["highest_genuine"]))
    print()
    cols = positive
    print(f"{'t':>5} " + " ".join(f"{g[:12]:>12}" for g in cols) + f" {'false fires':>14}")
    for r in res["sweep"]:
        cells = " ".join(f"{r[g]:12.0%}" if r[g] is not None else f"{'-':>12}" for g in cols)
        print(f"{r['t']:5.2f} {cells} {r['false']:5d} of {r['n_neg']:<5d}")
    s = res["suggestion"]
    print()
    if s is None:
        print(f"no threshold keeps false fires at or below {a.max_false}")
    else:
        what = "the hard slice" if hard else "the positives"
        print(f"suggestion: {s['threshold']:.2f} — catches {s['recall_target']:.0%} of {what} "
              f"with {s['false_fires']} genuine item(s) flagged. From one sample: confirm on "
              "held-out items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
