#!/usr/bin/env python3
"""The spread test (SKILL.md §2): can this question tell cases apart? stdlib only, no API.

    python scripts/spread.py RESPONSES.jsonl [...] [--threshold 0.5] [--min-n 20] [--json]

Reads System One answers you already have and, per question, prints where they sit. A
question whose answers all fall in a narrow band cannot gate anything: moving its
threshold only moves the rejection rate. Fix the question or drop it.

Input, one JSON object per line (formats are detected per line, so they can be mixed):

    {"id": "a", "scores": {"q1": 0.4, "q2": 0.9}, "labels": {"q1": true}}   wide
    {"id": "a", "question": "q1", "p": 0.4, "label": true}                    long
    {"answers": {"q1": {"type": "noul", "noul": 0.4}, ...}}                   a raw response
    {"response": {"answers": {...}}}                                          a cached one

`label` is optional: whether the question *should* fire on this item. With labels the
output adds AUC and the fire rate on each side. Scores and Choices are read as a number
too (a Score's expectation, a Choice's top weight) and scaled to 0-1 so the same bands apply.

Read the output the way §2 says to:

* the test **rejects, it does not select**: it tells you a question is a constant, never
  which of two working wordings is better. Spreads closer than 0.05 are noise below ~100
  items, and the script says so instead of ranking them;
* measure on the **unfiltered** population. A gate that has already rejected the high
  scorers makes its own question look flatter than it is;
* "never fires" is not "dead": check it against known-bad cases (use labels).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONSTANT_BELOW = 0.15  # the §2 table: 0.12-0.13 were constants, 0.25 discriminated
MARGINAL_BELOW = 0.20
NOISE = 0.05


@dataclass
class Series:
    name: str
    kind: str = "noul"
    values: list[float] = field(default_factory=list)
    labels: list[bool | None] = field(default_factory=list)

    def add(self, v: float, label: bool | None) -> None:
        self.values.append(v)
        self.labels.append(label)


def _answer_value(a: dict) -> tuple[float, str] | None:
    t = a.get("type", "")
    if t == "noul" or (t == "" and "noul" in a):
        v = a.get("noul")
        return (float(v), "noul") if v is not None else None
    if t == "score" or (t == "" and "score" in a):
        v = a.get("score")
        if v is None:
            return None
        levels = len(a.get("probabilities") or {}) or len(a.get("legend") or {})
        scale = max(levels - 1, 1)
        return float(v) / scale, "score"
    if t == "choice" or (t == "" and "choice" in a):
        probs = a.get("probabilities") or {}
        return (max(probs.values()), "choice") if probs else None
    return None


def read(paths: list[str]) -> dict[str, Series]:
    out: dict[str, Series] = {}

    def put(name: str, v, kind: str, label) -> None:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return
        out.setdefault(name, Series(name, kind)).add(float(v), label)

    for path in paths:
        fh = sys.stdin if path == "-" else open(path)
        with fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise SystemExit(f"{path}:{n}: not JSON ({exc})")
                row = row.get("response", row)
                if "answers" in row:
                    for q, a in row["answers"].items():
                        got = _answer_value(a)
                        if got:
                            put(q, got[0], got[1], None)
                elif "scores" in row:
                    labels = row.get("labels") or {}
                    for q, v in row["scores"].items():
                        put(q, v, "noul", labels.get(q, row.get("label")))
                elif "question" in row:
                    v = next((row[k] for k in ("p", "score", "noul", "value") if k in row), None)
                    put(row["question"], v, "noul", row.get("label"))
    return out


def quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(a positive outscores a negative), ties counting half. Mann-Whitney."""
    if not pos or not neg:
        return None
    ranked = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks = [0.0] * len(ranked)
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    r_pos = sum(r for r, (_, lab) in zip(ranks, ranked) if lab)
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def describe(s: Series, threshold: float) -> dict:
    v = s.values
    spread = statistics.pstdev(v) if len(v) > 1 else 0.0
    fired = sum(x >= threshold for x in v)
    d = {
        "question": s.name,
        "type": s.kind,
        "n": len(v),
        "median": statistics.median(v),
        "p10": quantile(v, 0.1),
        "p90": quantile(v, 0.9),
        "min": min(v),
        "max": max(v),
        "spread": spread,
        "fire_rate": fired / len(v),
    }
    d["verdict"] = (
        "nearly constant" if spread < CONSTANT_BELOW
        else "marginal" if spread < MARGINAL_BELOW
        else "discriminates"
    )
    notes = []
    if d["verdict"] == "nearly constant" and d["p90"] < threshold <= d["max"] and d["max"] >= 0.7:
        # Mostly low with a real tail: a rare-event question has little variance by nature.
        d["verdict"] = "rare event?"
        notes.append("low spread but it does reach high values: for a question about something "
                     "rare that is expected. Judge it on known positives (add labels), not on "
                     "its spread")
    if fired == 0:
        notes.append(f"never fires at {threshold:g}: nothing truncated, so the spread is "
                     "trustworthy — but is it a net or dead weight? check it on known-bad cases")
    elif d["fire_rate"] > 0.9:
        notes.append(f"fires on {d['fire_rate']:.0%} at {threshold:g}: it gates nothing")
    elif d["fire_rate"] < 0.02:
        notes.append(f"fires on {d['fire_rate']:.0%} at {threshold:g}: a threshold this far "
                     "out may suit a distribution the question does not have")
    labelled = [(x, lab) for x, lab in zip(v, s.labels) if lab is not None]
    if labelled:
        pos = [x for x, lab in labelled if lab]
        neg = [x for x, lab in labelled if not lab]
        d["auc"] = auc(pos, neg)
        d["n_pos"], d["n_neg"] = len(pos), len(neg)
        d["fires_on_pos"] = sum(x >= threshold for x in pos) / len(pos) if pos else None
        d["fires_on_neg"] = sum(x >= threshold for x in neg) / len(neg) if neg else None
        if d["auc"] is not None and d["auc"] < 0.6 and d["verdict"] != "nearly constant":
            notes.append(f"AUC {d['auc']:.2f}: wide but not pointing at your labels")
    d["notes"] = notes
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="JSONL files, or - for stdin")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--min-n", type=int, default=20, help="warn below this many items")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    series = read(args.files)
    if not series:
        print("no answers found", file=sys.stderr)
        return 2
    rows = [describe(s, args.threshold) for s in series.values()]
    rows.sort(key=lambda r: r["spread"])

    if args.json:
        json.dump(rows, sys.stdout, indent=1)
        print()
        return 0

    has_auc = any("auc" in r for r in rows)
    head = f"{'question':26} {'type':6} {'n':>6} {'median':>7} {'range':>11} {'spread':>7}"
    print(head + (f" {'AUC':>5} {'fires+':>6} {'fires-':>6}" if has_auc else "") + "  verdict")
    for r in rows:
        line = (f"{r['question'][:26]:26} {r['type']:6} {r['n']:6d} {r['median']:7.2f} "
                f"{r['min']:5.2f}-{r['max']:<5.2f} {r['spread']:7.2f}")
        if has_auc:
            a = r.get("auc")
            fp, fn = r.get("fires_on_pos"), r.get("fires_on_neg")
            line += (f" {a:5.2f}" if a is not None else "     -")
            line += (f" {fp:6.0%}" if fp is not None else "      -")
            line += (f" {fn:6.0%}" if fn is not None else "      -")
        print(line + f"  {r['verdict']}")
    print()
    for r in rows:
        for note in r["notes"]:
            print(f"- {r['question']}: {note}")
        if r["n"] < args.min_n:
            print(f"- {r['question']}: only {r['n']} items; a spread this small a sample is soft")
    close = [(a, b) for i, a in enumerate(rows) for b in rows[i + 1:]
             if a["verdict"] == b["verdict"] == "discriminates"
             and abs(a["spread"] - b["spread"]) < NOISE and min(a["n"], b["n"]) < 100]
    if close:
        names = ", ".join(f"{a['question']}≈{b['question']}" for a, b in close[:3])
        print(f"- spreads within {NOISE}: {names}. Under ~100 items that is noise; this test "
              "rejects constants, it does not rank working questions.")
    if all(r["n"] for r in rows):
        print("- measure on the unfiltered population: if an earlier gate already dropped the "
              "high scorers, these spreads read flatter than the question is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
