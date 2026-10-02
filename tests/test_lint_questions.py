import json
import textwrap

import lint_questions as L


def scan_src(tmp_path, name, src):
    (tmp_path / name).write_text(textwrap.dedent(src))
    qs, fs = L.scan([tmp_path])
    return qs, {f.rule for f in fs}, fs


def test_word_list_is_flagged_and_situation_is_not(tmp_path):
    _, rules, _ = scan_src(tmp_path, "a.py", '''
        from typesafe_sdk import Noul, NoulCriteria
        bad = Noul(instructions="Does the clip start mid-thought and carry on from earlier?",
                   criteria=NoulCriteria(true="Opens on 'and so', 'but then', 'yeah exactly'",
                                         false="Opens on a complete thought"))
        good = Noul(instructions="Does the opening depend on something the viewer was not given?",
                    criteria=NoulCriteria(
                        true="It finishes a thought that began earlier",
                        false="It carries enough on its own to follow from the first line"))
    ''')
    assert "word-list" in rules
    qs, _, fs = scan_src(tmp_path, "a.py", '''
        from typesafe_sdk import Noul, NoulCriteria
        good = Noul(instructions="Does the opening depend on something the viewer was not given?",
                    criteria=NoulCriteria(
                        true="It finishes a thought that began earlier",
                        false="It carries enough on its own to follow from the first line"))
    ''')
    assert len(qs) == 1 and not fs


def test_choice_needs_an_escape(tmp_path):
    _, rules, _ = scan_src(tmp_path, "c.py", '''
        from typesafe_sdk import Choice
        q = Choice(instructions="Which topic is this message mainly about?",
                   criteria={"billing": None, "bug": None})
    ''')
    assert "no-escape" in rules
    _, rules, _ = scan_src(tmp_path, "c.py", '''
        from typesafe_sdk import Choice
        q = Choice(instructions="Which topic is this message mainly about?",
                   criteria={"billing": None, "bug": None, "none_of_these": "neither"})
    ''')
    assert "no-escape" not in rules


def test_action_choice_is_only_info(tmp_path):
    _, _, fs = scan_src(tmp_path, "m.py", '''
        from typesafe_sdk import Choice
        q = Choice(instructions="Which move should Mario make right now?",
                   criteria={"run": "go", "jump": "hop"})
    ''')
    assert [f.severity for f in fs if f.rule == "no-escape"] == ["info"]


def test_dynamic_options_are_not_called_missing_an_escape(tmp_path):
    _, rules, _ = scan_src(tmp_path, "d.py", '''
        from typesafe_sdk import Choice
        def q(ids):
            return Choice(instructions="Which line is quoted? Choose `none_of_these` if none.",
                          criteria={i: None for i in ids})
    ''')
    assert "no-escape" not in rules


def test_score_levels(tmp_path):
    _, rules, _ = scan_src(tmp_path, "s.py", '''
        from typesafe_sdk import Score
        q = Score(instructions="How strong is the opening of this text?", criteria=["0", "1"])
    ''')
    assert "score-levels" in rules


def test_state_anchor_and_arithmetic_and_verdict(tmp_path):
    _, rules, _ = scan_src(tmp_path, "i.py", '''
        from typesafe_sdk import Choice
        a = Choice(instructions="A clip is cut around the line `region.moment`. Where should it start?",
                   criteria={"C0": None, "none_of_these": "none"})
        b = Choice(instructions="How many of these lines come before the quote? Pick the count.",
                   criteria={"1": None, "2": None, "none_of_these": "none"})
    ''')
    assert {"state-anchor", "arithmetic"} <= rules
    _, rules, _ = scan_src(tmp_path, "v.py", '''
        from typesafe_sdk import Noul, NoulCriteria
        q = Noul(instructions="Is this clip good and worth watching today?",
                 criteria=NoulCriteria(true="It is a strong piece of content for viewers",
                                       false="It is a weak piece of content for viewers"))
    ''')
    assert "verdict-question" in rules


def test_polarity_reads_the_stem_not_subordinate_clauses(tmp_path):
    _, rules, _ = scan_src(tmp_path, "p.py", '''
        from typesafe_sdk import Noul, NoulCriteria
        q = Noul(instructions="Could anyone resolve the ticket without looking inside the account?",
                 criteria=NoulCriteria(true="Resolving it requires seeing the account",
                                       false="It can be answered from general knowledge"))
    ''')
    assert "polarity" in rules
    _, rules, _ = scan_src(tmp_path, "p.py", '''
        from typesafe_sdk import Noul, NoulCriteria
        q = Noul(instructions="Does the first line answer a question that is not in the clip?",
                 criteria=NoulCriteria(true="It replies to something said before the clip",
                                       false="It stands without earlier context"))
    ''')
    assert "polarity" not in rules


def test_raw_dicts_helpers_and_structured_instructions(tmp_path):
    qs, _, _ = scan_src(tmp_path, "r.py", '''
        def noul(instructions, true, false):
            return {"type": "noul", "instructions": instructions,
                    "criteria": {"true": true, "false": false}}
        A = noul("Is the sender asking for a refund?", "They want money returned", "They do not")
        B = {"type": "choice", "instructions": {"question": "Which spot is best?", "goal": "survive"},
             "criteria": {"x": None}}
        C = {"type": "noul", "instructions": "Is the stack high enough that survival matters most?"}
    ''')
    kinds = sorted(q.kind for q in qs)
    assert kinds == ["choice", "noul", "noul"]  # the helper's template dict is not a question
    assert next(q for q in qs if q.kind == "choice").instructions.startswith("Which spot")
    assert any(q.true == "They want money returned" for q in qs)


def test_javascript_questions_do_not_borrow_the_next_ones_criteria(tmp_path):
    (tmp_path / "q.ts").write_text(textwrap.dedent('''
        const questions = {
          danger: { type: 'boolean',
            instructions:
              'If Mario keeps running right, will he be hit?',
          },
          move: { type: 'choice',
            instructions: 'Which move should Mario make?',
            criteria: { run: 'go right', jump: 'hop' } },
        }
    '''))
    qs, fs = L.scan([tmp_path])
    kinds = {q.kind for q in qs}
    assert kinds == {"noul", "choice"}
    move = next(q for q in qs if q.kind == "choice")
    assert set(move.options) == {"run", "jump"}


def test_json_questions(tmp_path):
    (tmp_path / "questions.json").write_text(json.dumps({
        "x": {"type": "noul", "instructions": "Does the message reveal a lasting fact about the user?",
              "criteria": {"true": "States something that stays true", "false": "Only about this task"}},
    }))
    qs, _ = L.scan([tmp_path])
    assert len(qs) == 1 and qs[0].true.startswith("States")


def test_skips_vendored_and_test_dirs_by_default(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("from typesafe_sdk import Noul\nq = Noul(instructions='long enough instruction text here')\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("from typesafe_sdk import Noul\nq = Noul(instructions='long enough instruction text here')\n")
    assert L.scan([tmp_path])[0] == []
    assert len(L.scan([tmp_path], include_tests=True)[0]) == 1


def test_fail_on_exit_status(tmp_path):
    (tmp_path / "a.py").write_text(
        "from typesafe_sdk import Choice\nq = Choice(instructions='Which topic is it about?', criteria={'a': None, 'b': None})\n")
    assert L.main([str(tmp_path), "--fail-on", "warn"]) == 1
    assert L.main([str(tmp_path)]) == 0


def test_javascript_choice_without_escape_is_flagged(tmp_path):
    (tmp_path / "q.js").write_text(
        "export const q = { type: 'choice', instructions: 'Which topic is the message about?',\n"
        "  criteria: { billing: null, bug: null } }\n")
    _, fs = L.scan([tmp_path])
    assert [f.rule for f in fs] == ["no-escape"]
