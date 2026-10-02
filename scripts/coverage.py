#!/usr/bin/env python3
"""Option-list coverage (SKILL.md §9): was the right answer ever on offer? stdlib only.

    python scripts/coverage.py CASES.jsonl [--tol 1.0] [--show 10] [--json]

A model cannot choose an option you did not offer, and in the logs that is
indistinguishable from a bad judgment. Before blaming the model, split every miss into
"never on the list" (fix the candidate generator) and "on the list but not chosen" (fix the
question). The first bounds what any question can achieve.

Input, one JSON object per line:

    {"id": "clip7",
     "offered": ["C00", "C01", "C02"]  or  {"C00": 12.5, "C01": 19.0, "C02": 31.2},
     "gold":    [19.5],                 # what would have been right
     "picked":  "C02",                  # optional: the option id the model chose
     "weights": {"C00": 0.1, ...}}      # optional: the Choice's probabilities

`offered` is a list of values or a mapping of option id -> value; `gold` are values. Strings
match when equal; numbers match within --tol (e.g. seconds). With `picked` the output also
says how often a correct option was offered *and* chosen, and with `weights` where the
correct option ranked and how much weight it got.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys


def matches(a, b, tol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


def analyse(case: dict, tol: float) -> dict:
    offered = case["offered"]
    if isinstance(offered, list):
        offered = {str(v): v for v in offered}
    gold = case.get("gold") or []
    right = [oid for oid, v in offered.items() if any(matches(v, g, tol) for g in gold)]
    row = {
        "id": case.get("id"),
        "n_offered": len(offered),
        "right_offered": right,
        "covered": bool(right),
    }
    picked = case.get("picked")
    if picked is not None:
        row["picked"] = str(picked)
        row["picked_right"] = str(picked) in right
    weights = case.get("weights")
    if weights and right:
        order = sorted(weights, key=lambda k: -weights[k])
        row["right_rank"] = min(order.index(r) + 1 for r in right if r in order) if any(
            r in order for r in right) else None
        row["right_weight"] = max(weights.get(r, 0.0) for r in right)
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="JSONL cases, or - for stdin")
    ap.add_argument("--tol", type=float, default=0.0, help="numeric tolerance for a match")
    ap.add_argument("--show", type=int, default=8, help="how many uncovered cases to list")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    fh = sys.stdin if args.file == "-" else open(args.file)
    with fh:
        rows = [analyse(json.loads(line), args.tol) for line in fh if line.strip()]
    if not rows:
        print("no cases", file=sys.stderr)
        return 2

    n = len(rows)
    covered = [r for r in rows if r["covered"]]
    out = {"cases": n, "covered": len(covered), "never_offered": n - len(covered),
           "coverage": len(covered) / n}
    judged = [r for r in rows if "picked_right" in r]
    if judged:
        hit = sum(r["picked_right"] for r in judged)
        out["picked_right"] = hit
        out["offered_not_picked"] = sum(r["covered"] and not r["picked_right"] for r in judged)
        out["accuracy"] = hit / len(judged)
        out["accuracy_when_offered"] = hit / max(1, sum(r["covered"] for r in judged))
    ranks = [r["right_rank"] for r in rows if r.get("right_rank")]
    if ranks:
        out["right_rank_median"] = statistics.median(ranks)
        out["right_weight_median"] = statistics.median(
            r["right_weight"] for r in rows if "right_weight" in r)
    if args.json:
        out["uncovered"] = [r["id"] for r in rows if not r["covered"]]
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0

    print(f"{n} cases")
    print(f"  right answer on the list   {len(covered):6d}  ({out['coverage']:.0%})   "
          "<- the ceiling for any question")
    print(f"  never offered              {n - len(covered):6d}  ({1 - out['coverage']:.0%})   "
          "<- fix the candidate generator, not the wording")
    if judged:
        print(f"  offered and picked         {out['picked_right']:6d}  ({out['accuracy']:.0%} "
              f"of all, {out['accuracy_when_offered']:.0%} of those offered)")
        print(f"  offered, not picked        {out['offered_not_picked']:6d}   "
              "<- the only misses a better question can fix")
    if ranks:
        print(f"  where the right option ranked: median {out['right_rank_median']:g}, "
              f"weight median {out['right_weight_median']:.2f}")
    dark = [r for r in rows if not r["covered"]]
    if dark and args.show:
        print(f"\nnever offered (first {min(args.show, len(dark))} of {len(dark)}):")
        for r in dark[: args.show]:
            print(f"  {r['id']}  ({r['n_offered']} options)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
