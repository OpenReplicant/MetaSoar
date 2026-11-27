"""E-18: the handler ladder on WikiTableQuestions (docs/experiments.md, E-18; design in e18-draft.md).

E-17d's rules (stream_v2.py: Wilson-bound promotion at 0.70, discard under 90% at n >= 5, demotion, every live candidate
observed on every label, a strict check), with these changes:
- Two levels of intent. A closed set of operation classes (CLASSES), chosen by d1-2B from their descriptions, "none"
  or a low probability going to `other`. Inside a class, fine intents as E-17d: the 6 nearest known fine intents of the
  class by embedding, d1-2B choosing; otherwise the small model names one, and a name that exists joins that intent
  (E-17d's suffix rule split 58 of 150 cases off). Keys are `class:name`.
- One handler per class, written by the large model from 3 labelled cases of the class on different tables (shortest
  tables first, different fine intents first), promoted and demoted on its agreement pooled over the class's labels.
  It is withdrawn for a fine intent that agrees on under 90% of 5 or more of that intent's labels (or under 50% of 3 or
  more, a clear misfit), and that intent's labels then leave its pool; a class handler is discarded (and rewritten once) only
  when it fails broadly, under 50% of 10 or more labels of the intents it still serves. Such an intent (and
  every intent of `other`) may get a handler of its own by E-17d's path. Templates stay per fine intent.
- A loose shape gate: a policy answers only loose shapes (`wtq_recurrence.coarse_shape`) it has agreed on. Whether
  E-17d's exact shape would also have admitted the case is recorded (`exact_admit`).
- Agreement by WTQ's evaluator (`agree`: `wtq.score` with either answer read as the gold list), so lists are sets.
- WTQ prompts (`smoke_wtq.prompt`), answers as comma-separated lists; the check refuses non-answers and placeholders,
  and allows lists. The large model's answers pass the same check, and a non-answer is never a label (from the pilot).
- The large model labels a case a cheaper rung answered while a cheaper candidate for it is in shadow (as E-17's
  shadow labels), so class handlers do not starve.

Gold is never read here. Usage: python3 -I stream_v3.py --chunk 1..9 --n 450 --chunk-size 50 --data DIR --out DIR
"""
from __future__ import annotations

import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import d1_intent  # noqa: E402
import smoke  # noqa: E402
import smoke_wtq  # noqa: E402
import stream  # noqa: E402
import stream_v2  # noqa: E402
import wtq  # noqa: E402
from wtq_recurrence import coarse_shape  # noqa: E402

CLASSES = {  # name: what d1-2B is shown
    "count": "Count the rows or items that meet a condition (how many ...)",
    "superlative": "Find the item with the largest or smallest value (most, highest, least, ...)",
    "ordinal": "Find the item at a position (the first, the last, the third, ...)",
    "comparison": "Compare two named items and say which one is higher, earlier, more ... (A or B)",
    "neighbour": "Find the row just before or just after a named row (next, previous, after, before)",
    "difference": "Compute the difference between two values (how many more, how much longer, ...)",
    "sum": "Add values up (the total, combined, altogether)",
    "average": "Compute an average or mean of values",
    "yes_no": "Answer yes or no about the table",
    "list": "List several items that meet a condition (name all, which ones, other than ...)",
    "filter": "Find the one item whose row meets a condition (the only one that ..., which one has no ..., the year when ...)",
    "lookup": "Read one value from the row that the question names (what, who, when, where, which)",
}
CLASS_INSTRUCTIONS = ("The state holds a question about a table. Which option describes the operation the question asks "
                      "for on the table, whatever its topic? Choose \"none\" if no option fits.")
FINE_INSTRUCTIONS = ("The state holds a question about a table. Which option's example question asks for the same "
                     "operation on a table (the same kind of computation), whatever the table's topic, columns, names or "
                     "numbers? Choose \"none\" if no option asks for the same operation.")
HANDLER = ("Write a Python function `solve(table, question, choices)` that answers every question of this kind from its "
           "table, with no model. The questions share an operation ({cls}: {desc}) but not a table: find the columns and "
           "values the question means from the question's words and the table's headers and cells; never rely on one "
           "table's column names. If you cannot find what the question means, raise an exception (the case then goes to "
           "a person). `table` maps each column name to a list of string cells; `choices` is None. Return the answer as "
           "a string, in the form of the examples; several answers as one string separated by ', '. Standard library "
           "only; parse numbers defensively.\n\nExamples:\n{examples}\n{redo}\nReply at once with one ```python code "
           "block and nothing else. Keep it under 60 lines.")
MAX_LEN, WITHDRAW_N, WITHDRAW_BELOW = 300, 5, 0.90
LARGE_TOKENS = 3000  # the pilot: at 1,500 some WTQ answers ran out inside the reasoning
MISFIT_N, MISFIT_BELOW = 3, 0.50  # a clear misfit is withdrawn sooner
CLASS_MIN_DISCARD, CLASS_DISCARD_BELOW = 10, 0.50  # a class handler is discarded (and rewritten) only when it fails
# broadly; one that fits some intents and not others is withdrawn from those, and promotion still needs the 0.70 bound


def agree(a, b):
    """WTQ's evaluator on two answers, either read as the gold list (sets, numbers, dates)."""
    if a is None or b is None:
        return False
    return any(wtq.score(a, items) for items in wtq.candidates(b)) or any(wtq.score(b, items) for items in wtq.candidates(a))


def strict(answer, case):
    a = stream.check(answer, case)
    if a is None:
        return None
    t = a.strip().strip(".")
    if stream_v2.NON_ANSWER.match(t) or stream_v2.PLACEHOLDER.search(t) or len(t) > MAX_LEN:
        return None
    return a


def choose_d1(question, options, instructions):
    crit = dict(options, none="None of these")
    d = d1_intent.post(8083, "/v1/systemone", {"state": {"question": question},
                                               "questions": {"q": {"type": "choice", "instructions": instructions,
                                                                   "criteria": crit}}})
    return {k: float(v) for k, v in d["answers"]["q"]["probabilities"].items()}


def embed_tables(texts):
    d = d1_intent.post(8084, "/v1/embeddings", {"model": "embed", "input": [
        f"Instruct: Given a question about a table, represent the operation it asks for\nQuery:{t}" for t in texts]})
    return [x["embedding"] for x in sorted(d["data"], key=lambda x: x["index"])]


class StreamV3(stream_v2.StreamV2):
    def __init__(self, *a, choose3_fn=None, **kw):
        kw.setdefault("embed_fn", embed_tables)
        self.choose3 = choose3_fn or choose_d1
        super().__init__(*a, **kw)
        self.state.setdefault("classes", {})

    def rejudge(self):  # a new stream: nothing to re-judge
        self.state["rules"] = "v3"
        self.save()

    # ---- intents
    def classify(self, case):
        opts = {f"c{j}": d for j, d in enumerate(CLASSES.values())}
        p = self.choose3(case["question"], opts, CLASS_INSTRUCTIONS)
        best = max(p, key=p.get)
        self._route = {"class_p": round(p[best], 3)}
        if best == "none" or p[best] < stream_v2.D1_MIN:
            return "other"
        return list(CLASSES)[int(best[1:])]

    def elaborate(self, case):
        cls = self.classify(case)
        members, first = {}, {}
        for r in self.state["cases"]:
            if r["intent"].split(":")[0] == cls:
                members.setdefault(r["intent"], []).append(r["id"])
                first.setdefault(r["intent"], r["id"])
        v = self.vector(case)
        cos = lambda x, y: sum(i * j for i, j in zip(x, y))
        sims = {g: max(cos(v, self.vector(self.byid[m])) for m in ms) for g, ms in members.items()}
        near = sorted(sims, key=lambda g: -sims[g])[:stream_v2.K_NEAR]
        self._route.update(cls=cls, near=near, by="new")
        if near:
            p = self.choose3(case["question"], {f"o{j}": self.byid[first[g]]["question"] for j, g in enumerate(near)},
                             FINE_INSTRUCTIONS)
            best = max(p, key=p.get)
            self._route.update(d1=best, p=round(p[best], 3))
            if best != "none" and p[best] >= stream_v2.D1_MIN:
                self._route["by"] = "d1"
                return near[int(best[1:])]
        key = f"{cls}:{self.name_intent(case, cls)}"
        if key in self.state["intents"]:
            self._route["by"] = "merged"  # E-17d's lesson: join the named intent instead of splitting
        return key

    def name_intent(self, case, cls):
        """The small model's key, as stream.Stream.elaborate, shown only the names of this class's intents."""
        known = ", ".join(k.split(":", 1)[1] for k in self.state["intents"] if k.split(":")[0] == cls) or "(none yet)"
        text = self.small.ask(stream.ELABORATE.format(known=known, question=case["question"]), stream.INTENT_TOKENS)
        text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S)
        found = re.findall(r"Intent:[ \t]*([^\n]*)", text)
        if not found:
            return "unknown"
        key = re.split(r"<|end with|[ _]or[ _]", found[0], flags=re.I)[0]
        return "_".join(stream.norm_key(key).split("_")[:4])

    # ---- one case
    def process(self, case, chunk):
        s0 = (self.large.snap(), self.small.snap())
        intent = self.elaborate(case)
        cls = intent.split(":")[0]
        new = intent not in self.state["intents"]
        it = self.state["intents"].setdefault(intent, {"n": 0, "labelled": [], "class": cls,
                                                       "candidates": {"handler": None, "template": None}})
        ct = self.state["classes"].setdefault(cls, {"labelled": [], "handler": None, "write_failures": 0})
        it["n"] += 1
        rung, answer, fb, text, exact = self.decide_apply(case, it)
        shadow_label = False
        if rung == "large":
            if answer:  # a non-answer (empty, a placeholder echoed) is never a label
                self.retain_label(intent, it, case, answer, text)
        elif self.cheaper_in_shadow(rung, it, ct):
            ltext = self.large.ask(smoke_wtq.prompt(case), LARGE_TOKENS)
            label = strict(smoke.extract(ltext), case)
            if label:
                self.retain_label(intent, it, case, label, ltext)
            shadow_label = True
        s1 = (self.large.snap(), self.small.snap())
        rec = {"id": case["id"], "chunk": chunk, "intent": intent, "class": cls, "new_intent": new, "rung": rung,
               "answer": answer, "fallback": fb is not None, "fallback_from": fb, "shadow_label": shadow_label,
               "exact_admit": exact, "large": stream.delta(s0[0], s1[0]), "small": stream.delta(s0[1], s1[1]),
               "route": self._route, "shape": coarse_shape(case), "exact_shape": stream_v2.shape(case)}
        self.state["cases"].append(rec)
        self.done.add(case["id"])
        self.save()
        return rec

    def cheaper_in_shadow(self, rung, it, ct):
        order = ["fine_handler", "class_handler", "template"]
        if rung not in order:
            return False
        cands = {"fine_handler": it["candidates"]["handler"], "class_handler": ct["handler"],
                 "template": it["candidates"]["template"]}
        return any(c and c["status"] == "shadow" for k, c in cands.items() if order.index(k) < order.index(rung))

    def policies(self, it):
        """The policies that may answer this intent, cheapest first."""
        ct = self.state["classes"][it["class"]]
        out = [("fine_handler", it["candidates"]["handler"])]
        if it["class"] != "other" and not it.get("withdrawn"):
            out.append(("class_handler", ct["handler"]))
        out.append(("template", it["candidates"]["template"]))
        return out

    def decide_apply(self, case, it):
        """-> (rung, answer, fallback_from, large text, exact_admit)."""
        loose, exact = coarse_shape(case), stream_v2.shape(case)
        for rung, c in self.policies(it):
            if c and c["status"] == "active" and loose in c.get("shapes", []):
                got, _ = self.run_candidate(c, case)
                if got is not None:
                    return rung, got, None, None, exact in c.get("exact_shapes", [])
                c["fallbacks"] = c.get("fallbacks", 0) + 1
                fb = rung
                break
        else:
            fb = None
        text = self.large.ask(smoke_wtq.prompt(case), LARGE_TOKENS)
        return "large", strict(smoke.extract(text), case) or "", fb, text, None

    def run_candidate(self, c, case):
        if c["kind"] == "handler":
            raw, err = stream.run_handler(c["code"], case)
            got = strict(raw, case) if err is None else None
            return got, raw if err is None else err
        raw = smoke.extract(self.small.ask(f"Here is a plan for problems of this kind:\n{c['text']}\n\nFollow the plan "
                                           f"on the new problem.\n\n{smoke_wtq.prompt(case)}"))
        return strict(raw, case), raw

    # ---- judge
    def observe(self, it, kind, c, label, stats=None):
        if stats is not None and it.get("withdrawn"):
            return  # a withdrawn intent no longer counts for or against the class handler
        case = self.byid[label["id"]]
        got, detail = self.run_candidate(c, case)
        ok = got is not None and agree(got, label["answer"])
        c["n"] += 1
        c["agree"] += ok
        if stats is not None:
            stats["n"] += 1
            stats["agree"] += ok
        if ok:
            c["shapes"] = sorted(set(c.get("shapes", [])) | {coarse_shape(case)})
            c["exact_shapes"] = sorted(set(c.get("exact_shapes", [])) | {stream_v2.shape(case)})
        else:
            c["failures"] = (c["failures"] + [{"id": label["id"], "expected": label["answer"], "got": detail}])[-5:]
        if c.get("scope") == "class":
            self.judge_class(c)
        else:
            self.judge(it, kind, c)

    def judge_class(self, c):
        lb = stream_v2.wilson_lower(c["agree"], c["n"])
        if c["status"] == "active" and lb < stream_v2.LOWER:
            c["status"], c["demoted"] = "shadow", c.get("demoted", 0) + 1
        elif c["status"] == "shadow" and lb >= stream_v2.LOWER:
            c["status"] = "active"
        elif c["status"] == "shadow" and c["n"] >= CLASS_MIN_DISCARD and c["agree"] / c["n"] < CLASS_DISCARD_BELOW:
            c["status"] = "discarded"
            if c["rewrites"] == 0:
                self.write_class_handler(c["class"], rewrite=c)

    def withdraw_if_misfit(self, it, c):
        """Withdraw the class handler from a fine intent it disagrees with, and take that intent out of its pool."""
        st = it.get("class_stats")
        if not st or it.get("withdrawn"):
            return
        rate = st["agree"] / st["n"] if st["n"] else 1.0
        if (st["n"] >= WITHDRAW_N and rate < WITHDRAW_BELOW) or (st["n"] >= MISFIT_N and rate < MISFIT_BELOW):
            it["withdrawn"] = True
            c["n"] -= st["n"]
            c["agree"] -= st["agree"]
            self.judge_class(c)

    def retain_label(self, intent, it, case, answer, text):
        label = {"id": case["id"], "answer": answer, "text": text, "intent": intent}
        it["labelled"].append(label)
        ct = self.state["classes"][it["class"]]
        ct["labelled"].append(label)
        for kind in ("handler", "template"):
            c = it["candidates"][kind]
            if c and c["status"] in ("shadow", "active"):
                self.observe(it, kind, c, label)
        h = ct["handler"]
        if h and h["status"] in ("shadow", "active") and it["class"] != "other":
            stats = it.setdefault("class_stats", {"n": 0, "agree": 0})
            self.observe(it, "handler", h, label, stats)
            self.withdraw_if_misfit(it, h)
        self.compile(it)
        if it["class"] != "other" and ct["handler"] is None and ct["write_failures"] < 2:
            self.write_class_handler(it["class"])

    def compile(self, it):
        wf = it.setdefault("write_failures", {"handler": 0, "template": 0})
        kinds = ["template"] + (["handler"] if it.get("withdrawn") or it["class"] == "other" else [])
        for kind in kinds:
            if it["candidates"][kind] is None and len(it["labelled"]) >= self.k + wf[kind] and wf[kind] < 2:
                self.compile_one(it, kind)

    def examples_for(self, labelled, n=3):
        """Labelled cases on different tables, different fine intents first, shortest tables first."""
        by_len = sorted(labelled, key=lambda r: len(self.byid[r["id"]]["table"]))
        out, tables, intents = [], set(), set()
        for prefer_new_intent in (True, False):
            for r in by_len:
                t = self.byid[r["id"]]["table"]
                if len(out) < n and t not in tables and (not prefer_new_intent or r["intent"] not in intents):
                    out.append(r)
                    tables.add(t)
                    intents.add(r["intent"])
        return out if len(out) == n else None

    def write_class_handler(self, cls, rewrite=None):
        ct = self.state["classes"][cls]
        ex = self.examples_for(ct["labelled"])
        if ex is None:
            return  # not yet 3 labelled cases on different tables
        fails = (rewrite or {}).get("failures", [])
        redo = ""
        if rewrite:
            redo = ("Your earlier version gave wrong answers here (earlier code below). Fix it.\n" +
                    "\n\n".join(stream.show(self.byid[f["id"]], f["expected"]) + f"\nYour answer: {f['got']}" for f in fails[:3]) +
                    f"\nEarlier code:\n```python\n{rewrite['code']}\n```\n")
        text = self.large.ask(HANDLER.format(cls=cls, desc=CLASSES[cls], examples="\n\n".join(
            stream.show(self.byid[r["id"]], r["answer"]) for r in ex), redo=redo), stream.HANDLER_TOKENS,
            stream.HANDLER_PREFILL)
        code = stream.code_block(text)
        if code:
            try:
                compile(code, "handler", "exec")
            except SyntaxError:
                code = None
        if not code:
            if not rewrite:
                ct["write_failures"] += 1
            return
        c = {"kind": "handler", "scope": "class", "class": cls, "version": (rewrite["version"] + 1) if rewrite else 1,
             "rewrites": 1 if rewrite else 0, "used": [r["id"] for r in ex], "n": 0, "agree": 0, "failures": [],
             "fallbacks": 0, "status": "shadow", "shapes": [], "exact_shapes": [], "code": code}
        ct["handler"] = c
        for it in self.state["intents"].values():  # per-intent agreement restarts with a new version
            if it.get("class") == cls:
                it.pop("class_stats", None)
                it.pop("withdrawn", None)
        for r in ct["labelled"]:
            if c["status"] != "shadow":
                break
            if r["id"] not in c["used"]:
                it = self.state["intents"][r["intent"]]
                self.observe(it, "handler", c, r, it.setdefault("class_stats", {"n": 0, "agree": 0}))
                self.withdraw_if_misfit(it, c)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chunk", type=int, required=True)
    stream.add_model_flags(ap)
    a = ap.parse_args()
    large, small = stream.build_models(a)
    s = StreamV3(a.data, a.out, large, small, a.chunk_size, a.n)
    t = time.time()
    try:
        s.run_chunk(a.chunk)
    except stream.ChunkError as e:
        sys.exit(str(e))
    print(f"chunk {a.chunk} done in {time.time() - t:.0f} s: large {s.large.snap()} small {s.small.snap()}")


if __name__ == "__main__":
    main()
