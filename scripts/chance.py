#!/usr/bin/env python3
"""The chance baseline (SKILL.md §2, corollary): a hit rate means nothing alone. stdlib only.

A method that fires often hits often by luck. Report what random picks would score at the
same density, and how far above it you are. Two modes.

PICKS: you choose k of n items and some are right.

    python scripts/chance.py picks --n 200 --positives 30 --k 40 --observed 18
    python scripts/chance.py picks --cases cases.jsonl --observed 120

  `--cases` is JSONL of {"offered": n, "gold": g} (one per Choice): the expected top-1
  accuracy of a random pick is the mean of g/n. For a single pool the hit count is
  hypergeometric, so the p-value is exact.

SPANS: you place clips of given lengths on a timeline and matched labeled ones (IoU > 0.5),
  the way jevcut's evaluate.py does.

    python scripts/chance.py spans --duration 3600 --lengths 40,55,38 \\
        --labels 100-140,900-950 --observed-recall 0.5

  Random placement, seeded, averaged over --trials; match is one-to-one best-IoU first.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys


def hypergeom_sf(n: int, k_pos: int, draws: int, observed: int) -> float:
    """P(X >= observed) drawing `draws` from n items of which k_pos are positive."""
    hi = min(draws, k_pos)
    lo = max(0, draws - (n - k_pos))
    total = math.comb(n, draws)
    return sum(math.comb(k_pos, x) * math.comb(n - k_pos, draws - x)
               for x in range(max(observed, lo), hi + 1)) / total


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def match_count(pred: list[tuple[float, float]], gold: list[tuple[float, float]],
                min_iou: float) -> int:
    pairs = sorted(((iou(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gold)
                    if iou(p, g) > min_iou), reverse=True)
    used_p: set[int] = set()
    used_g: set[int] = set()
    for _, i, j in pairs:
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
    return len(used_p)


def span_chance(lengths: list[float], gold: list[tuple[float, float]], duration: float,
                trials: int = 300, seed: int = 0, min_iou: float = 0.5) -> float:
    """Mean recall of clips of those lengths dropped uniformly at random."""
    if not lengths or not gold or duration <= 0:
        return 0.0
    rng = random.Random(seed)
    total = 0.0
    for _ in range(trials):
        spans = []
        for length in lengths:
            t0 = rng.uniform(0.0, max(duration - length, 0.0))
            spans.append((t0, t0 + length))
        total += match_count(spans, gold, min_iou) / len(gold)
    return total / trials


def _spans(text: str) -> list[tuple[float, float]]:
    out = []
    for part in text.split(","):
        a, _, b = part.strip().partition("-")
        out.append((float(a), float(b)))
    return out


def cmd_picks(a: argparse.Namespace) -> int:
    if a.cases:
        gs = []
        with open(a.cases) as fh:
            for line in fh:
                if line.strip():
                    c = json.loads(line)
                    gs.append(min(1.0, c["gold"] / c["offered"]))
        expected = sum(gs)
        print(f"{len(gs)} choices: a random pick is right {expected / len(gs):.1%} of the time "
              f"({expected:.1f} of {len(gs)})")
        if a.observed is not None:
            print(f"observed {a.observed} -> {a.observed / max(expected, 1e-9):.1f}x chance")
        return 0
    if None in (a.n, a.positives, a.k):
        raise SystemExit("picks needs --n, --positives and --k (or --cases)")
    precision = a.positives / a.n
    print(f"random picks hit {precision:.1%} of the time -> {a.k * precision:.1f} of {a.k} "
          f"expected; recall at that density {min(1.0, a.k / a.n):.1%}")
    if a.observed is not None:
        exp = a.k * precision
        p = hypergeom_sf(a.n, a.positives, a.k, a.observed)
        print(f"observed {a.observed}: {a.observed / max(exp, 1e-9):.1f}x chance, "
              f"P(chance does this well) = {p:.3g}")
    return 0


def cmd_spans(a: argparse.Namespace) -> int:
    lengths = [float(x) for x in a.lengths.split(",")]
    gold = _spans(a.labels)
    c = span_chance(lengths, gold, a.duration, a.trials, a.seed, a.iou)
    print(f"{len(lengths)} random clips against {len(gold)} labeled: chance recall {c:.1%}")
    if a.observed_recall is not None:
        print(f"observed {a.observed_recall:.1%} -> {a.observed_recall / max(c, 1e-9):.1f}x chance")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("picks", help="k picks from n items")
    p.add_argument("--n", type=int)
    p.add_argument("--positives", type=int)
    p.add_argument("--k", type=int)
    p.add_argument("--observed", type=int)
    p.add_argument("--cases")
    p.set_defaults(fn=cmd_picks)
    s = sub.add_parser("spans", help="clips placed on a timeline")
    s.add_argument("--duration", type=float, required=True)
    s.add_argument("--lengths", required=True, help="comma-separated clip lengths")
    s.add_argument("--labels", required=True, help="comma-separated start-end pairs")
    s.add_argument("--observed-recall", type=float)
    s.add_argument("--trials", type=int, default=300)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--iou", type=float, default=0.5)
    s.set_defaults(fn=cmd_spans)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
