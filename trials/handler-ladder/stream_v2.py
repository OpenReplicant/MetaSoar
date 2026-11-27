"""E-17d: the handler ladder with E-17b's three fixes (docs/experiments.md). `stream.py` stays as E-17 and E-17b ran it.

1. Promotion on evidence. A candidate is promoted when the 95% Wilson lower bound of its agreement with the large
   model is at least 0.70 (9 agreements of 9 at the least, in place of 3 of 3), discarded when it agrees on under
   90% of n >= 5, and demoted to shadow when an active candidate's bound falls below 0.70. Every candidate that is
   not discarded is observed on every new label, so active ones keep being judged.
2. Shapes. A table's shape is its number of columns, the kind of cells in each (number, list of numbers, time, text,
   blank) and whether choices are given. A promoted candidate answers only shapes it has agreed on; a case of a shape
   it has not seen goes to the large model, whose label then counts for or against the candidate on that shape.
3. A stricter check: a candidate's answer is refused when it is a non-answer ("None", "null", "n/a", empty), holds
   a placeholder (`<...>`, "the answer only"), is a list of numbers where no choices are given, or is over 100
   characters.
4. Intents by d1-2B. The known intents nearest the question (the 6 with the largest cosine of Qwen3-Embedding-0.6B
   vectors to any earlier question of the intent) are offered to d1-2B, each by its first question, with "none of
   these"; a choice at probability >= 0.3 is the intent. Otherwise the small model names a new intent as before (a
   name already taken gets a suffix, since d1-2B judged it different).
On start, a state from the earlier rules is re-judged: every candidate that is not discarded is run again on its
intent's labelled cases (not those it was written from) and its status set by these rules.

Gold is never read here, as in stream.py. Serving: `../decision-readout/serve.sh ladder` and `serve.sh elabcpu`.
Usage: python3 -I stream_v2.py --chunk 10|11|12 --n 600 --chunk-size 50 --out results-e17d
"""
from __future__ import annotations

import argparse, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import d1_intent  # noqa: E402  (embed, d1_choose: :8084, :8083)
import stream  # noqa: E402

LOWER, DISCARD_BELOW, MIN_DISCARD = 0.70, 0.90, 5
K_NEAR, D1_MIN = 6, 0.3
NON_ANSWER = re.compile(r"^(none|null|nan|n/?a|undefined|unknown|error|\?)$", re.I)
PLACEHOLDER = re.compile(r"<[^>]*>|the answer only", re.I)
NUMBER_LIST = re.compile(r"-?\d+(\.\d+)?\s*,\s+-?\d")  # '0, 0, 6, 8' (a thousands comma has no space)


def wilson_lower(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def cell_kind(x):
    x = str(x).strip()
    if not x or x == "?":
        return "blank"
    if re.fullmatch(r"\$?-?[\d,]*\.?\d+%?", x):
        return "num"
    if re.fullmatch(r"-?\d+(\.\d+)?(\s*,\s*-?\d+(\.\d+)?)+", x):
        return "list"
    if re.fullmatch(r"\d{1,2}:\d{2}\s*[AP]\.?M\.?", x, re.I):
        return "time"
    return "text"


def shape(case):
    cols = case.get("table_for_pd") or {}
    kinds = tuple("|".join(sorted({cell_kind(x) for x in col})) for col in cols.values())
    return f"{len(cols)}:{','.join(kinds)}:{'choices' if case.get('choices') else 'open'}"


def strict(answer, case):
    """stream.check, then refuse non-answers. -> the answer or None."""
    a = stream.check(answer, case)
    if a is None:
        return None
    t = a.strip().strip(".")
    if NON_ANSWER.match(t) or PLACEHOLDER.search(t) or len(t) > 100:
        return None
    if not case.get("choices") and NUMBER_LIST.search(t):
        return None
    return a


class StreamV2(stream.Stream):
    def __init__(self, *a, embed_fn=None, choose_fn=None, **kw):
        super().__init__(*a, **kw)
        self.embed_fn, self.choose_fn = embed_fn or d1_intent.embed, choose_fn or d1_intent.d1_choose
        self.vec_path = os.path.join(self.dir, "vectors.json")
        self.vec = {}
        if os.path.exists(self.vec_path):
            with open(self.vec_path) as f:
                self.vec = json.load(f)
        self.embed_done()
        if not self.state.get("rules") == "v2":
            self.rejudge()

    # ---- 4. intents
    def vector(self, case):
        if case["id"] not in self.vec:
            self.vec[case["id"]] = self.embed_fn([case["question"]])[0]
        return self.vec[case["id"]]

    def embed_done(self):
        todo = [self.byid[r["id"]] for r in self.state["cases"] if r["id"] not in self.vec]
        for i in range(0, len(todo), 16):
            for c, v in zip(todo[i:i + 16], self.embed_fn([c["question"] for c in todo[i:i + 16]])):
                self.vec[c["id"]] = v

    def save(self):
        super().save()
        if hasattr(self, "vec"):
            with open(self.vec_path + ".tmp", "w") as f:
                json.dump(self.vec, f)
            os.replace(self.vec_path + ".tmp", self.vec_path)

    def elaborate(self, case):
        members, first = {}, {}
        for r in self.state["cases"]:
            members.setdefault(r["intent"], []).append(r["id"])
            first.setdefault(r["intent"], r["id"])
        v = self.vector(case)
        cos = lambda a, b: sum(x * y for x, y in zip(a, b))
        sims = {g: max(cos(v, self.vector(self.byid[m])) for m in ms) for g, ms in members.items()}
        near = sorted(sims, key=lambda g: -sims[g])[:K_NEAR]
        self._route = {"by": "new", "near": near}
        if near:
            p = self.choose_fn(case["question"], {f"o{j}": self.byid[first[g]]["question"] for j, g in enumerate(near)})
            best = max(p, key=p.get)
            self._route.update(d1=best, p=round(p[best], 3))
            if best != "none" and p[best] >= D1_MIN:
                self._route["by"] = "d1"
                return near[int(best[1:])]
        key = base = super().elaborate(case)
        j = 2
        while key in self.state["intents"]:
            key, j = f"{base[:36]}_v{j}", j + 1
        return key

    def process(self, case, chunk):
        rec = super().process(case, chunk)
        rec["route"], rec["shape"] = self._route, shape(case)
        self.save()
        return rec

    # ---- 2, 3. apply
    def decide_apply(self, case, it):
        fallback_from, sh = None, shape(case)
        for kind in ("handler", "template"):
            c = it["candidates"][kind]
            if c and c["status"] == "active" and sh in c.get("shapes", []):
                got, _ = self.run_candidate(c, case)
                if got is not None:
                    return kind, got, None, None
                c["fallbacks"] = c.get("fallbacks", 0) + 1
                fallback_from = kind
                break
        text = self.large.ask(stream.smoke.prompt(case), stream.LARGE_TOKENS)
        raw = stream.smoke.extract(text)
        return "large", stream.check(raw, case) or raw or "", fallback_from, text

    def run_candidate(self, c, case):
        got, detail = super().run_candidate(c, case)
        if got is not None and strict(got, case) is None:
            return None, f"refused: {got!r}"
        return got, detail

    # ---- 1. judge
    def retain_label(self, intent, it, case, answer, text):
        it["labelled"].append({"id": case["id"], "answer": answer, "text": text})
        for kind in ("handler", "template"):
            c = it["candidates"][kind]
            if c and c["status"] in ("shadow", "active"):
                self.observe(it, kind, c, it["labelled"][-1])
        self.compile(it)

    def observe(self, it, kind, c, label):
        case = self.byid[label["id"]]
        got, detail = self.run_candidate(c, case)
        ok = got is not None and stream.same(got, label["answer"])
        c["n"] += 1
        c["agree"] += ok
        if ok:
            c["shapes"] = sorted(set(c.get("shapes", [])) | {shape(case)})
        else:
            c["failures"] = (c["failures"] + [{"id": label["id"], "expected": label["answer"], "got": detail}])[-5:]
        self.judge(it, kind, c)

    def judge(self, it, kind, c):
        lb = wilson_lower(c["agree"], c["n"])
        if c["status"] == "active" and lb < LOWER:
            c["status"], c["demoted"] = "shadow", c.get("demoted", 0) + 1
        elif c["status"] == "shadow" and lb >= LOWER:
            c["status"] = "active"
        elif c["status"] == "shadow" and c["n"] >= MIN_DISCARD and c["agree"] / c["n"] < DISCARD_BELOW:
            c["status"] = "discarded"
            if c["rewrites"] == 0:
                self.compile_one(it, kind, rewrite=c)

    def rejudge(self):
        for it in self.state["intents"].values():
            for kind in ("handler", "template"):
                c = it["candidates"][kind]
                if not c or c["status"] == "discarded":
                    continue
                c.update(n=0, agree=0, failures=[], shapes=[], status="shadow", v1_status=c["status"])
                for r in it["labelled"]:
                    if r["id"] not in c["used"] and c["status"] != "discarded":
                        self.observe(it, kind, c, r)
        self.state["rules"] = "v2"
        self.save()

    def compile_one(self, it, kind, rewrite=None):
        super().compile_one(it, kind, rewrite)
        c = it["candidates"][kind]
        if c is not None:
            c.setdefault("shapes", [])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chunk", type=int, required=True)
    stream.add_model_flags(ap)
    a = ap.parse_args()
    large, small = stream.build_models(a)
    s = StreamV2(a.data, a.out, large, small, a.chunk_size, a.n)
    try:
        s.run_chunk(a.chunk)
    except stream.ChunkError as e:
        sys.exit(str(e))
    print(f"chunk {a.chunk} done: large {s.large.snap()} small {s.small.snap()}")


if __name__ == "__main__":
    main()
