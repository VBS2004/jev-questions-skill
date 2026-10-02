# jev-questions

A [Claude Code](https://claude.com/claude-code) skill for designing typed questions for
Jev / [TypeSafe](https://docs.typesafe.ai/models.md) System One: Noul, Choice and Score.

It is a field guide to writing questions that mean something, and to debugging the ones
that don't: a question that fires on everything, one that fires on nothing, a Choice that
picks something implausible. Every rule comes with a number that was measured while
building [jevcut](https://github.com/VBS2004/jevcut), an auto-clipper built on Jev, and
several were learned by getting them wrong first.

The rules are about System One in general, not clipping. They apply to any judge, gate,
filter, classifier or extractor built on it.

## What's in it

1. Criteria describe situations, never words
2. Check that your question can discriminate (the spread test)
3. Pick the primitive for the shape of the judgment
4. State: put the model exactly where the judge sits
5. Many questions, one state, one request
6. Do not ask for a number you are about to compute
7. Separate judgment from policy
8. Know where the model actually beats code
9. Failure patterns that look like model errors

## Install

```bash
git clone https://github.com/VBS2004/jev-questions-skill ~/.claude/skills/jev-questions
```

Claude Code loads it when you build or debug a System One question. You can also just read
[SKILL.md](SKILL.md); it is plain Markdown.

## License

[MIT](LICENSE).
