import json
import math
import random

import chance as C
import coverage as V
import threshold as T


def test_coverage_splits_never_offered_from_offered_not_picked():
    cases = [
        {"id": "a", "offered": ["x", "y"], "gold": ["y"], "picked": "y"},
        {"id": "b", "offered": {"C0": 1.0, "C1": 9.0}, "gold": [20.0], "picked": "C1"},
        {"id": "c", "offered": {"C0": 1.0, "C1": 19.6}, "gold": [20.0], "picked": "C0",
         "weights": {"C0": 0.7, "C1": 0.3}},
    ]
    rows = [V.analyse(c, 1.0) for c in cases]
    assert [r["covered"] for r in rows] == [True, False, True]
    assert [r["picked_right"] for r in rows] == [True, False, False]
    assert rows[2]["right_rank"] == 2 and rows[2]["right_weight"] == 0.3


def test_coverage_numeric_tolerance_is_inclusive():
    assert V.matches(10.0, 11.0, 1.0) and not V.matches(10.0, 11.01, 1.0)
    assert V.matches("a", "a", 0.0) and not V.matches("a", "b", 5.0)


def test_coverage_cli(tmp_path, capsys):
    p = tmp_path / "c.jsonl"
    p.write_text('{"id":"a","offered":[1,2],"gold":[2]}\n{"id":"b","offered":[1],"gold":[9]}\n')
    assert V.main([str(p), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["coverage"] == 0.5 and out["uncovered"] == ["b"]


def test_hypergeometric_matches_brute_force():
    n, k_pos, draws = 12, 5, 4
    total = hit = 0
    from itertools import combinations
    for comb in combinations(range(n), draws):
        total += 1
        hit += sum(i < k_pos for i in comb) >= 3
    assert abs(C.hypergeom_sf(n, k_pos, draws, 3) - hit / total) < 1e-12
    assert abs(C.hypergeom_sf(n, k_pos, draws, 0) - 1.0) < 1e-12


def test_span_chance_is_zero_when_nothing_can_match_and_seeded():
    assert C.span_chance([10.0], [(0.0, 100.0)], 1000.0) == 0.0  # IoU 0.1 never exceeds 0.5
    a = C.span_chance([40.0, 40.0], [(100.0, 140.0)], 1000.0, seed=3)
    assert a == C.span_chance([40.0, 40.0], [(100.0, 140.0)], 1000.0, seed=3) and a > 0


def test_span_match_is_one_to_one():
    pred = [(0.0, 10.0), (0.0, 10.0)]
    assert C.match_count(pred, [(0.0, 10.0)], 0.5) == 1


def test_iou():
    assert C.iou((0, 10), (5, 15)) == 5 / 15 and C.iou((0, 1), (2, 3)) == 0.0


def test_picks_cli(capsys):
    assert C.main(["picks", "--n", "200", "--positives", "30", "--k", "40", "--observed", "18"]) == 0
    out = capsys.readouterr().out
    assert "6.0 of 40" in out and "3.0x chance" in out


def _groups():
    rnd = random.Random(1)
    g = {"content": [(f"c{i}", rnd.uniform(0.0, 0.4)) for i in range(100)],
         "whole": [(f"w{i}", rnd.uniform(0.85, 1.0)) for i in range(20)],
         "middle": [(f"m{i}", rnd.uniform(0.6, 0.95)) for i in range(20)]}
    g["middle"][0] = ("m0", 0.2)  # one hard case below the genuine peak
    return g


def test_threshold_suggests_a_bar_between_peak_and_hard_slice():
    g = _groups()
    peak = max(s for _, s in g["content"])
    res = T.analyse(g, ["whole", "middle"], ["middle"], ["content"], "high",
                    T.parse_grid("0.2:0.8:0.05"), 0)
    s = res["suggestion"]
    assert s["false_fires"] == 0 and s["threshold"] > peak
    assert s["recall_target"] == 19 / 20  # the 0.2 middle is unreachable without flagging content


def test_threshold_max_false_trades_recall_for_false_fires():
    g = _groups()
    strict = T.analyse(g, ["whole", "middle"], ["middle"], ["content"], "high", [], 0)["suggestion"]
    loose = T.analyse(g, ["whole", "middle"], ["middle"], ["content"], "high", [], 50)["suggestion"]
    assert loose["recall_target"] >= strict["recall_target"] and loose["false_fires"] > 0


def test_threshold_low_direction():
    g = {"ok": [("a", 0.8), ("b", 0.9)], "bad": [("c", 0.1), ("d", 0.3)]}
    res = T.analyse(g, ["bad"], [], ["ok"], "low", [0.2, 0.5], 0)
    assert res["genuine_peak"] == 0.8 and res["suggestion"]["recall_target"] == 1.0


def test_threshold_cli(tmp_path, capsys):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps({"id": f"{g}{i}", "group": g, "score": s})
                           for g, items in _groups().items() for i, (_, s) in enumerate(items)))
    assert T.main([str(p), "--positive", "whole;middle", "--hard", "middle", "--negative", "content"]) == 0
    assert "suggestion:" in capsys.readouterr().out
