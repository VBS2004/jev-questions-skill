"""Score the ad check on jevcut's labeled texts, from the response cache, for threshold.py.

    uv run python promotion_scores.py --out /tmp/promo     # run from a jevcut checkout

Reuses eval/experiments/promotion_context.py's items (labeled sponsor reads whole and cut
to their middle, genuine clips, and three ads a real run shipped) and writes one JSONL per
way of asking: <out>.alone.jsonl and <out>.context.jsonl, rows {"id", "group", "score"}.
Replay only: a missing cache entry is an error, never a request.
"""
import argparse
import json
import sys
from dataclasses import replace

sys.path.insert(0, "eval/experiments")
from promotion_context import CONTEXT_QUESTION, items  # noqa: E402

from jevcut.client import JevClient  # noqa: E402
from jevcut.config import Config  # noqa: E402
from jevcut.questions import promotion_questions  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
a = ap.parse_args()
config = replace(Config(), cache_mode="replay", max_requests_per_video=10**6,
                 max_tokens_per_video=10**9)
rows = items()


def ask(client, state, questions):
    try:
        return client.ask(state, questions, pass_name="promotion").answers["promotion"].noul
    except Exception as exc:  # noqa: BLE001 - a CacheMiss: the wording is part of the cache key
        ask.last = f"{type(exc).__name__}: {str(exc)[:120]}"
        return None


ask.last = ""
counts = {"alone": 0, "context": 0}
with JevClient(config) as client, open(f"{a.out}.alone.jsonl", "w") as alone, \
        open(f"{a.out}.context.jsonl", "w") as ctx:
    for it in rows:
        ident = f"{it['video']}:{it['name']}"
        for name, fh, p in (
            ("alone", alone, ask(client, {"clip": {"text": it["text"]}}, promotion_questions())),
            ("context", ctx, ask(client, {"clip": {"text": it["text"]},
                                          "around": {"before": it["before"],
                                                     "after": it["after"]}}, CONTEXT_QUESTION)),
        ):
            if p is not None:
                fh.write(json.dumps({"id": ident, "group": it["group"], "score": p}) + "\n")
                counts[name] += 1
print(f"{len(rows)} items: {counts['context']} scored with context, {counts['alone']} alone "
      f"(the alone wording was replaced, so its cache entries no longer match: {ask.last})",
      file=sys.stderr)
