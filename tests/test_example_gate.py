import gate as G


def fake_ask(values):
    def ask(state, questions):
        assert set(questions) == set(G.QUESTIONS)  # every question in ONE request
        return {
            "is_not_a_request": {"noul": values.get("spam", 0.0)},
            "needs_account_access": {"noul": values.get("acct", 0.0)},
            "is_urgent": {"noul": values.get("urgent", 0.0)},
            "topic": {"choice": values.get("topic", "bug"),
                      "probabilities": values.get("weights", {"bug": 0.9, "none_of_these": 0.1})},
        }
    return ask


def test_irreparable_is_checked_first():
    j = G.judge("x", fake_ask({"spam": 0.9, "urgent": 0.99, "acct": 0.99}))
    assert G.verdict(j)["action"] == "drop"  # urgency never rescues spam


def test_fixable_things_come_back_as_instructions_not_a_bare_no():
    j = G.judge("x", fake_ask({"acct": 0.9, "urgent": 0.9}))
    v = G.verdict(j)
    assert v["action"] == "escalate" and v["todo"] == ["verify the sender before touching their account"]


def test_escape_option_and_weak_topic_both_mean_no_topic():
    esc = G.judge("x", fake_ask({"topic": G.NONE, "weights": {G.NONE: 0.9, "bug": 0.1}}))
    weak = G.judge("x", fake_ask({"topic": "bug", "weights": {"bug": 0.4, "billing": 0.4, G.NONE: 0.2}}))
    assert G.verdict(esc)["topic"] is None and G.verdict(weak)["topic"] is None
    assert "ask which area" in G.verdict(esc)["todo"][0]


def test_thresholds_change_the_verdict_without_new_judgment():
    j = G.judge("x", fake_ask({"urgent": 0.6}))
    assert G.verdict(j)["action"] == "escalate"
    assert G.verdict(j, {**G.THRESHOLDS, "is_urgent": 0.7})["action"] == "queue"


def test_example_passes_its_own_linter():
    import lint_questions as L
    from pathlib import Path
    _, findings = L.scan([Path(G.__file__)])
    assert [f for f in findings if f.severity == "warn"] == []


def test_dry_run_needs_no_key(capsys):
    assert G.main(["--dry", "I was charged twice today"]) == 0
    assert '"action"' in capsys.readouterr().out
