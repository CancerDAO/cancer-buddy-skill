# SYNTHETIC-example — what this one page is and is not

**Is:** a worked example of the annotation format in `../README.md` §4, and a way to
exercise the evaluator contract (§5) on a machine with no patient archive present.

**Is not:** a benchmark. One page measures nothing. Accuracy numbers only mean something
against the 42-page local gold set described in `../README.md` §2, which is never
committed.

## Regenerating the page

```bash
python3 tests/fixtures/organize-gold/SYNTHETIC-example/make_fixture.py
```

The PDF is generated rather than committed, so no binary enters git and the page can
never drift from the script that defines it. `page-001.expected.frontmatter.yaml` is
hand-written to match `make_fixture.py`'s `LINES`; change one and change the other.

## Walking it through the v3 path

```bash
P=$(mktemp -d)/patient && mkdir -p "$P/raw/incoming"
python3 tests/fixtures/organize-gold/SYNTHETIC-example/make_fixture.py --out "$P/raw/incoming"
ORG=skills/cancer-buddy-organize
python3 $ORG/scripts/prepare_pages.py "$P" --run-id gold --model-id <host-model> \
        --source SYN001=raw/incoming/page-001.pdf
```

`pages.json` must report `text_layer_kind: born_digital` for this page. That is itself a
checkable expectation, and it is the one the rest of the pipeline keys off: on a
born-digital page the text layer is the character truth and an independent CHANNEL, so
every high-risk field above should come back `settled_via: text_layer` from
`plan_second_read.py` and cost no model call at all.

A run where this page needs a second read is a signal worth chasing — either
`prepare_pages.py` misclassified the text layer, or the transcription rewrote values the
text layer already stated.
