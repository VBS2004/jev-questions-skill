import json

import spread as S


def write(tmp_path, rows):
    p = tmp_path / "r.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_constant_vs_discriminating(tmp_path):
    rows = [{"scores": {"flat": 0.66 + (i % 3) * 0.02, "wide": i / 19}} for i in range(20)]
    series = S.read([write(tmp_path, rows)])
    flat, wide = (S.describe(series[k], 0.5) for k in ("flat", "wide"))
    assert flat["verdict"] == "nearly constant" and wide["verdict"] == "discriminates"
    assert abs(wide["spread"] - ((20**2 - 1) / 12) ** 0.5 / 19) < 1e-9  # pop. stdev of i/19


def test_formats_are_equivalent(tmp_path):
    wide = write(tmp_path, [{"scores": {"q": 0.2}}, {"scores": {"q": 0.8}}])
    long = tmp_path / "l.jsonl"
    long.write_text('{"question": "q", "p": 0.2}\n{"question": "q", "p": 0.8}\n')
    raw = tmp_path / "w.jsonl"
    raw.write_text('{"answers": {"q": {"type": "noul", "noul": 0.2}}}\n'
                   '{"response": {"answers": {"q": {"type": "noul", "noul": 0.8}}}}\n')
    vals = [sorted(S.read([str(p)])["q"].values) for p in (wide, long, raw)]
    assert vals[0] == vals[1] == vals[2] == [0.2, 0.8]


def test_score_and_choice_are_scaled_to_unit_range(tmp_path):
    p = write(tmp_path, [
        {"answers": {"hook": {"type": "score", "score": 3.0, "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1}},
                     "pick": {"type": "choice", "choice": "a", "probabilities": {"a": 0.6, "b": 0.4}}}}])
    s = S.read([p])
    assert s["hook"].values == [1.0] and s["pick"].values == [0.6]


def test_auc_known_values():
    assert S.auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert S.auc([0.1], [0.9]) == 0.0
    assert S.auc([0.5, 0.5], [0.5, 0.5]) == 0.5  # all ties
    assert abs(S.auc([0.9, 0.4], [0.5, 0.1]) - 0.75) < 1e-12  # 3 of 4 pairs


def test_rare_event_is_not_called_constant(tmp_path):
    # 2% of items are real positives: stdev ~0.12, under the constant line, yet it has a tail
    rows = [{"scores": {"rare": 0.05}} for _ in range(98)] + [{"scores": {"rare": 0.9}} for _ in range(2)]
    d = S.describe(S.read([write(tmp_path, rows)])["rare"], 0.5)
    assert d["verdict"] == "rare event?"


def test_gates_nothing_and_never_fires_notes(tmp_path):
    hi = S.describe(S.read([write(tmp_path, [{"scores": {"q": 0.88}} for _ in range(10)])])["q"], 0.5)
    assert any("gates nothing" in n for n in hi["notes"])
    lo = S.describe(S.read([write(tmp_path, [{"scores": {"q": 0.1 + i / 100}} for i in range(10)])])["q"], 0.5)
    assert any("never fires" in n for n in lo["notes"])


def test_labels_add_auc_and_fire_rates(tmp_path):
    rows = [{"scores": {"q": 0.9}, "label": True}, {"scores": {"q": 0.8}, "label": True},
            {"scores": {"q": 0.2}, "label": False}, {"scores": {"q": 0.6}, "label": False}]
    d = S.describe(S.read([write(tmp_path, rows)])["q"], 0.5)
    assert d["auc"] == 1.0 and d["fires_on_pos"] == 1.0 and d["fires_on_neg"] == 0.5


def test_main_runs_and_reports(tmp_path, capsys):
    p = write(tmp_path, [{"scores": {"a": i / 10, "b": 0.5}} for i in range(11)])
    assert S.main([p]) == 0
    out = capsys.readouterr().out
    assert "nearly constant" in out and "discriminates" in out


def test_reads_stdin(monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('{"scores": {"q": 0.1}}\n{"scores": {"q": 0.9}}\n'))
    assert S.main(["-", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["n"] == 2
