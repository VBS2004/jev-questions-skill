"""For every labeled clip jevcut found, was the labeled start among the openings offered?

    uv run python openings_coverage.py > cases.jsonl    # run from a jevcut checkout
    python SKILL_DIR/scripts/coverage.py cases.jsonl --tol 1.0

Same replay as eval/experiments/opening_misses.py (the opening Choice answered from the
response cache, no requests), but written out as coverage.py cases: `offered` maps each
marked candidate opening to its time, `gold` is the labeler's start, `picked` and
`weights` are the Choice's answer. Cases are limited to far-off clips by --far (seconds)
when given, since those are where the question "never offered, or offered and missed?"
matters.
"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, "eval/experiments")
from opening_misses import LABELS, RUN, opening_answer  # noqa: E402

from jevcut import cuts as cuts_mod  # noqa: E402
from jevcut import evaluate  # noqa: E402
from jevcut import search as search_mod  # noqa: E402
from jevcut.backends import load_env  # noqa: E402
from jevcut.client import JevClient  # noqa: E402
from jevcut.config import Config  # noqa: E402
from jevcut.edl import read_edl  # noqa: E402
from jevcut.models import Transcript  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--far", type=float, default=0.0, help="only clips whose start is this far off")
a = ap.parse_args()

load_env()
config = replace(Config(), cache_mode="replay")
n = 0
with JevClient(replace(config, max_requests_per_video=100_000)) as client:
    for d in LABELS:
        for f in sorted(Path(d).glob("*.json")):
            label = json.loads(f.read_text())
            stem = Path(label["video"]["local_path"]).stem
            t = Transcript.from_json(f"eval/media/asr-lemonfox/{stem}.json")
            real = search_mod._real(cuts_mod.extract(t, config))
            _, clips = read_edl(Path("eval/media") / f"{stem}{RUN}" / "edl.json")
            gold = label["clips"]
            pairs = evaluate.match([(c.t0, c.t1) for c in clips],
                                   [(g["start"], g["end"]) for g in gold])
            for i, j in pairs:
                c, g = clips[i], gold[j]
                if abs(c.t0 - g["start"]) < a.far:
                    continue
                marks, pick = opening_answer(client, t, real, t.by_id(c.anchor_id), config)
                print(json.dumps({
                    "id": f"{Path(d).name}/{stem}/{c.id}",
                    "offered": {m: s for m, (s, _) in marks.items()},
                    "gold": [g["start"]],
                    "picked": pick,
                    "weights": {m: w for m, (_, w) in marks.items()},
                }))
                n += 1
print(f"{n} cases", file=sys.stderr)
