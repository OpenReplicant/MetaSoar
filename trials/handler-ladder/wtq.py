"""E-18 preparation: WikiTableQuestions (WTQ) as cases for the handler-ladder runner (docs/experiments.md, E-18).

WTQ: Pasupat and Liang, ACL 2015, https://arxiv.org/abs/1508.00305. Repository https://github.com/ppasupat/WikiTableQuestions,
licence CC BY-SA 4.0 (its `LICENSE` file at the pinned commit). Pinned: tag v1.0.2, commit REV. The data is fetched,
not committed (`trials/data/` is ignored), as TabMWP is.

Three things here:
- `fetch`: downloads the release's compact zip, checks its SHA-256 and unpacks it.
- `build`: writes `problems_<split>.json` in the shape of TabMWP's file, so `stream.load_cases(data_dir)` works
  unchanged on a directory that holds `problems_test1k.json`. Each problem has the runner's fields (`question`,
  `choices` None, `table`, `table_for_pd`, `table_title`, `unit` None) and, for the scorer only, `answer` (the
  gold strings, as WTQ's `targetValue`), `answer_canon` (CoreNLP's canonical forms, `targetCanon`), `answer_type`
  and `table_id`. The runner copies only `PROBLEM_FIELDS`, so none of the four reaches it (the same wall as TabMWP's).
- `correct(pred, problem)`: WTQ's official scoring, ported from `evaluator.py` (Python 2) at the pinned commit.

Usage (data in its own directory, paths as arguments):
    python3 -I wtq.py fetch ../data/wtq-84dd647
    python3 -I wtq.py build ../data/wtq-84dd647 ../data/wtq-84dd647-problems       # test1k, dev1k, test
"""
from __future__ import annotations

import argparse, hashlib, json, os, random, re, sys, unicodedata, urllib.request, zipfile
from math import isinf, isnan

REV = "84dd647e7a2b47661e990c490d63b49d0b84c42a"  # tag v1.0.2 (2017-02-16)
ZIP_URL = "https://github.com/ppasupat/WikiTableQuestions/releases/download/v1.0.2/WikiTableQuestions-1.0.2-compact.zip"
ZIP_SHA256 = "7c9ca7cc1ccd75fe4be0255b44be63f7b566761005f4ee6ce67e51c129d8b085"
ZIP_BYTES = 29267445
LICENCE = "CC BY-SA 4.0"
# split name -> (source file in tagged/data, sample size or None for all, sampling seed)
SPLITS = {"test1k": ("pristine-unseen-tables", 1000, 18), "dev1k": ("training", 1000, 18),
          "test": ("pristine-unseen-tables", None, 0)}


# ---- fetch -------------------------------------------------------------------------------------------------------

def fetch(dest):
    """Download and unpack the pinned release into `dest` (an empty or missing directory)."""
    if os.path.isdir(dest) and os.listdir(dest):
        raise SystemExit(f"{dest} is not empty")
    os.makedirs(dest, exist_ok=True)
    z = os.path.join(dest, "wtq.zip")
    with urllib.request.urlopen(ZIP_URL, timeout=300) as r, open(z, "wb") as f:
        f.write(r.read())
    h = hashlib.sha256(open(z, "rb").read()).hexdigest()
    if h != ZIP_SHA256:
        raise SystemExit(f"checksum mismatch: {h}")
    with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():
            rel = m.split("/", 1)[1] if "/" in m else ""  # drop the top-level "WikiTableQuestions/"
            if not rel or ".." in rel.split("/") or rel.startswith("/"):
                continue
            target = os.path.join(dest, rel)
            if m.endswith("/"):
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(zf.read(m))
    os.remove(z)


# ---- tables and cases --------------------------------------------------------------------------------------------

def tsv_unescape(x):
    """WTQ's TSV escapes: `\\n` newline, `\\p` pipe, `\\\\` backslash (README, 'TSV Format')."""
    return x.replace(r"\n", "\n").replace(r"\p", "|").replace("\\\\", "\\")


def one_line(x):
    return re.sub(r"\s+", " ", tsv_unescape(x)).strip()


def parse_table(text):
    """A table's TSV text -> (columns, rows). Headers are made unique and non-empty; ragged rows are padded."""
    lines = text.split("\n")
    while lines and not lines[-1]:
        lines.pop()
    head = [one_line(h) for h in lines[0].split("\t")]
    seen, cols = {}, []
    for i, h in enumerate(head):
        h = h or f"col{i + 1}"
        seen[h] = seen.get(h, 0) + 1
        cols.append(h if seen[h] == 1 else f"{h} ({seen[h]})")
    rows = [[one_line(c) for c in ln.split("\t")] for ln in lines[1:]]
    rows = [(r + [""] * len(cols))[:len(cols)] for r in rows]
    return cols, rows


def table_case(cols, rows):
    """-> (table, table_for_pd): the rows as ' | '-joined text with the header first, and column -> string cells."""
    text = "\n".join(" | ".join(r) for r in [cols] + rows)
    return text, {c: [r[i] for r in rows] for i, c in enumerate(cols)}


def problem(example, root):
    """One WTQ example (a dict of the .tagged fields) -> a TabMWP-shaped problem."""
    with open(os.path.join(root, example["context"].replace(".csv", ".tsv")), encoding="utf8") as f:
        cols, rows = parse_table(f.read())
    table, pd = table_case(cols, rows)
    return {"question": tsv_unescape(example["utterance"]), "choices": None, "table": table, "table_for_pd": pd,
            "table_title": None, "unit": None,  # the compact release has no page titles (only the full one does)
            "answer": [tsv_unescape(x) for x in example["targetValue"].split("|")],
            "answer_canon": [tsv_unescape(x) for x in example["targetCanon"].split("|")],
            "answer_type": example["targetCanonType"], "table_id": example["context"]}


def read_examples(path):
    with open(path, encoding="utf8") as f:
        head = f.readline().rstrip("\n").split("\t")
        return [dict(zip(head, ln.rstrip("\n").split("\t"))) for ln in f if ln.strip()]


def build(root, out_dir, splits=SPLITS):
    os.makedirs(out_dir, exist_ok=True)
    for name, (src, n, seed) in splits.items():
        ex = read_examples(os.path.join(root, "tagged", "data", src + ".tagged"))
        if n:
            ex = random.Random(seed).sample(sorted(ex, key=lambda e: e["id"]), n)
        probs = {e["id"]: problem(e, root) for e in sorted(ex, key=lambda e: e["id"])}
        with open(os.path.join(out_dir, f"problems_{name}.json"), "w") as f:
            json.dump(probs, f)
        print(f"problems_{name}.json: {len(probs)} problems")


# ---- scoring: the official evaluator, ported ---------------------------------------------------------------------

def normalize(x):
    """evaluator.py `normalize`: no diacritics, ASCII quotes and dashes, no trailing citations or (details), no
    outer quotes, no final period, lower case, single spaces."""
    x = "".join(c for c in unicodedata.normalize("NFKD", x) if unicodedata.category(c) != "Mn")
    x = re.sub(r"[‘’´`]", "'", x)
    x = re.sub(r"[“”]", '"', x)
    x = re.sub(r"[‐‑‒–—−]", "-", x)
    while True:
        old = x
        x = re.sub(r"((?<!^)\[[^\]]*\]|\[\d+\]|[•♦†‡*#+])*$", "", x.strip())
        x = re.sub(r"(?<!^)( \([^)]*\))*$", "", x.strip())
        x = re.sub(r'^"([^"]*)"$', r"\1", x.strip())
        if x == old:
            break
    if x and x[-1] == ".":
        x = x[:-1]
    return re.sub(r"\s+", " ", x).lower().strip()


def parse_number(text):
    """int(text), else float(text) when finite, else None (as the official `NumberValue.parse`; '1,000' is not a number)."""
    if "_" in text:  # Python 3 accepts 1_000; Python 2 did not
        return None
    try:
        return int(text)
    except ValueError:
        try:
            a = float(text)
            return None if isnan(a) or isinf(a) else a
        except ValueError:
            return None


def parse_date(text):
    """'yyyy-mm-dd' with 'xx' for unknown fields -> (y, m, d) with -1 for unknown, else None."""
    try:
        ymd = text.lower().split("-")
        assert len(ymd) == 3
        y = -1 if ymd[0] in ("xx", "xxxx") else int(ymd[0])
        m = -1 if ymd[1] == "xx" else int(ymd[1])
        d = -1 if ymd[2] == "xx" else int(ymd[2])
        assert not (y == m == d == -1)
        assert m == -1 or 1 <= m <= 12
        assert d == -1 or 1 <= d <= 31
        return y, m, d
    except (AssertionError, ValueError):
        return None


class Value:
    """kind 's' string, 'n' number, 'd' date; `norm` the normalised original string."""

    def __init__(self, kind, key, norm):
        self.kind, self.key, self.norm = kind, key, norm

    def __eq__(self, o):
        return (self.kind, self.key) == (o.kind, o.key)

    def __hash__(self):
        return hash((self.kind, self.key))

    def match(self, other):
        if self.norm == other.norm:
            return True
        if self.kind == "n" and other.kind == "n":
            return abs(self.key - other.key) < 1e-6
        if self.kind == "d" and other.kind == "d":
            return self.key == other.key
        return False


def to_value(original, canon=None):
    amount = parse_number(canon or original)
    if amount is not None:
        a = int(amount) if abs(amount - round(amount)) < 1e-6 else float(amount)
        return Value("n", a, normalize(original) if original else str(a))
    ymd = parse_date(canon or original)
    if ymd is not None:
        if ymd[1] == ymd[2] == -1:
            return Value("n", ymd[0], normalize(original))
        return Value("d", ymd, normalize(original))
    return Value("s", normalize(original), normalize(original))


def to_values(strings, canons=None):
    if canons is None:
        return list({to_value(s) for s in strings})
    return list({to_value(s, c) for s, c in zip(strings, canons)})


def check_denotation(target, predicted):
    """Same size, and every target item matches some predicted item (set semantics, as official)."""
    return len(target) == len(predicted) and all(any(t.match(p) for p in predicted) for t in target)


SPLITTERS = (r"\s*\n\s*", r"\s*\|\s*", r";\s*", r",\s+", r"\s+and\s+",
             r"\s*\n\s*|\s*\|\s*|;\s*|,\s+(?:and\s+)?|\s+and\s+")


def candidates(pred):
    """The readings of a model's answer as a list of items. The text as one item first (a cell such as 'Paris, France'
    is one item); then, for a list answer, the text split on newlines, '|', ';', ', ' or ' and '."""
    if isinstance(pred, (list, tuple)):
        return [[str(x) for x in pred]]
    out = [[pred]]
    for rx in SPLITTERS:
        parts = [p for p in re.split(rx, pred.strip()) if p.strip()]
        if len(parts) > 1 and parts not in out:
            out.append(parts)
    return out


def score(pred, gold, canon=None):
    """True when `pred` (a string or a list of strings) is the official-correct denotation of `gold`."""
    if pred is None:
        return False
    target = to_values(gold, canon)
    return any(check_denotation(target, to_values(items)) for items in candidates(pred))


def correct(pred, p):
    """The scorer's entry, as `smoke.correct(pred, p)`: p holds `answer` (list) and optionally `answer_canon`."""
    gold = p["answer"] if isinstance(p["answer"], list) else [str(p["answer"])]
    return score(pred, gold, p.get("answer_canon"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").add_argument("dest")
    b = sub.add_parser("build")
    b.add_argument("root")
    b.add_argument("out")
    a = ap.parse_args()
    fetch(a.dest) if a.cmd == "fetch" else build(a.root, a.out)


if __name__ == "__main__":
    main()
