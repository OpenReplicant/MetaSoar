"""E-17 stream runner: the handler ladder on a stream of TabMWP cases (docs/experiments.md, docs/handler-ladder.md).

Per case: a small model names the intent; the cheapest promoted policy of that intent answers (handler, template,
large model); every answer is checked, and a failed check or an error falls back to the large model. Cases the
large model answers become that intent's labelled cases (its answer is the label, never gold). Enough labelled
cases compile a handler (large model writes Python) and a template (small model generalises a solution); a
candidate is promoted when it agrees with the large model's answers at >= 95% on n >= 3 cases it was not written
from, and discarded below that at n >= 5 (rewritten once, with its failures shown).

Gold answers are never read here: `load_cases` copies only the fields in PROBLEM_FIELDS. Scoring is summarize.py.

Usage: python3 -I stream.py --chunk 1|2|3     (state in results/state.json; resumes exactly; chunks run in order)
"""
from __future__ import annotations

import argparse, json, os, random, re, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I does not put the script's directory on the path
import smoke  # noqa: E402  (prompt, extract, number, DATA)

PROBLEM_FIELDS = ("question", "choices", "table", "table_for_pd", "table_title", "unit")
K, THRESHOLD, MIN_PROMOTE, MIN_DISCARD = 3, 0.95, 3, 5
LARGE_EXTRA = {"reasoning_effort": "none"}
SMALL_EXTRA = {"chat_template_kwargs": {"enable_thinking": False}}

ELABORATE = ("Name the intent of the question below as one short snake_case key (2 to 4 words) for the kind of "
             "computation it asks for, with no names, numbers or topic words. If a known intent fits, reuse it "
             "exactly.\nKnown intents: {known}\n\nQuestion: {question}\n\nEnd with one line: Intent: <key>")
HANDLER = ("Write a Python function `solve(table, question, choices)` that answers every question of this kind "
           "from its table, with no model. `table` maps each column name to a list of string cells, `question` is "
           "the question text, `choices` is a list of strings or None. Return the answer as a string, in the form "
           "of the examples (when choices exist, return one choice as written). Standard library only; parse "
           "numbers defensively (strip $ , % and units).\n\nExamples:\n{examples}\n{redo}\nReply with one "
           "```python code block.")
TEMPLATE = ("Rewrite this worked solution as a generic plan for any problem of this kind: numbered steps, every "
            "specific name, number and value removed. Output only the plan.\n{redo}\nSolution:\n{text}")
HARNESS = '''
import json, os, sys
try:
    import resource
    for r, v in ((resource.RLIMIT_CPU, 5), (resource.RLIMIT_AS, 1 << 30), (resource.RLIMIT_FSIZE, 1 << 20)):
        resource.setrlimit(r, (v, v))
except Exception:
    pass
import socket
def _no(*a, **k):
    raise OSError("network disabled")
socket.socket = socket.create_connection = socket.getaddrinfo = _no
args = json.load(sys.stdin)
real, sys.stdout = sys.stdout, open(os.devnull, "w")
ns = {}
exec(compile(open("handler.py").read(), "handler.py", "exec"), ns)
real.write(json.dumps({"out": str(ns["solve"](args["table"], args["question"], args["choices"]))}))
'''


# ---- models -----------------------------------------------------------------------------------------------------

def http_model(url, model, extra):
    """An OpenAI-style chat endpoint as fn(text, max_tokens) -> (content, usage)."""
    def fn(text, max_tokens=700):
        body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
                "temperature": 0, **extra}
        req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.load(r)
        return d["choices"][0]["message"]["content"] or "", d.get("usage", {})
    return fn


class Meter:
    """Wraps a model function (injectable, so tests use fakes) and counts calls, tokens and wall seconds."""

    def __init__(self, fn):
        self.fn, self.calls, self.prompt_tokens, self.completion_tokens, self.seconds = fn, 0, 0, 0, 0.0

    def ask(self, text, max_tokens=700):
        t = time.perf_counter()
        try:
            out, usage = self.fn(text, max_tokens)
        finally:
            self.seconds += time.perf_counter() - t
            self.calls += 1
        self.prompt_tokens += usage.get("prompt_tokens") or 0
        self.completion_tokens += usage.get("completion_tokens") or 0
        return out

    def snap(self):
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "seconds": self.seconds}


def delta(a, b):
    return {k: round(b[k] - a[k], 3) if k == "seconds" else b[k] - a[k] for k in b}


# ---- data, answers, checks ---------------------------------------------------------------------------------------

def stream_ids(ids, n=300):
    ids = sorted(ids)
    random.Random(17).shuffle(ids)
    return ids[:n]


def load_cases(data_dir=smoke.DATA, n=300):
    """The stream's cases in order, with only PROBLEM_FIELDS (no gold, no annotation)."""
    with open(os.path.join(data_dir, "problems_test1k.json")) as f:
        probs = json.load(f)
    return [{"id": i, **{f: probs[i].get(f) for f in PROBLEM_FIELDS}} for i in stream_ids(probs, n)]


def norm_key(s):
    """Intent key: lowercase [a-z0-9_], at most 40 characters."""
    s = re.sub(r"[^a-z0-9_]+", "_", (s or "").lower().replace("`", "")).strip("_")
    return re.sub(r"_+", "_", s)[:40].strip("_") or "unknown"


def full_number(s):
    t = s.strip().replace(",", "").replace("$", "").rstrip("%").strip()
    return smoke.number(t) if re.fullmatch(r"-?(\d+\.?\d*|\.\d+)(/\d+)?", t) else None


def lead_number(s):
    m = re.match(r"\s*\$?(-?[\d,]*\.?\d+(?:/\d+)?)\s*%?\s*[A-Za-z][\w .'-]*$", s)
    return smoke.number(m.group(1).replace(",", "")) if m else None


def same(a, b):
    """Agreement: numbers as numbers (a bare number also equals number + unit words), other text case-folded."""
    if a is None or b is None:
        return False
    na, nb = full_number(a), full_number(b)
    if na is None and nb is not None:
        na = lead_number(a)
    elif nb is None and na is not None:
        nb = lead_number(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= 1e-6 * max(1, abs(nb))
    return a.strip().strip(".").casefold() == b.strip().strip(".").casefold()


def check(answer, case):
    """The answer (mapped onto its choice when choices exist), or None if empty / not one of the choices."""
    a = (answer or "").strip().strip("*").strip()
    if not a:
        return None
    choices = case.get("choices")
    if not choices:
        return a
    for c in choices:
        if c.strip().casefold() == a.strip(".").casefold():
            return c
    return next((c for c in choices if same(a, c)), None)


def run_handler(code, case, timeout=5):
    """Run `solve` in a fresh `python3 -I` subprocess (5 s, rlimits, sockets disabled, temp dir). -> (answer, error)."""
    args = {"table": {k: [str(x) for x in v] for k, v in (case.get("table_for_pd") or {}).items()},
            "question": case["question"], "choices": case.get("choices")}
    with tempfile.TemporaryDirectory() as d:
        for name, body in (("handler.py", code), ("harness.py", HARNESS)):
            with open(os.path.join(d, name), "w") as f:
                f.write(body)
        try:
            r = subprocess.run([sys.executable, "-I", "harness.py"], input=json.dumps(args), cwd=d, env={},
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, "timeout"
    if r.returncode:
        return None, (r.stderr.strip().splitlines() or ["error"])[-1]
    try:
        return json.loads(r.stdout)["out"], None
    except Exception:
        return None, "bad output"


def code_block(text):
    blocks = [b for b in re.findall(r"```(?:python)?\s*\n(.*?)```", text or "", re.S) if "def solve" in b]
    return blocks[-1].strip() if blocks else None


def show(case, answer=None):
    lines = [f"Question: {case['question']}"]
    if case.get("choices"):
        lines.append("Choices: " + "; ".join(case["choices"]))
    lines.append("Table: " + json.dumps(case.get("table_for_pd")))
    if answer is not None:
        lines.append(f"Answer: {answer}")
    return "\n".join(lines)


# ---- the stream --------------------------------------------------------------------------------------------------

class ChunkError(RuntimeError):
    pass


class Stream:
    def __init__(self, data_dir, out_dir, large, small, chunk_size=100, n=300, k=K, log=print):
        self.cases = load_cases(data_dir, n)
        self.byid = {c["id"]: c for c in self.cases}
        self.large, self.small = Meter(large), Meter(small)
        self.dir, self.chunk_size, self.k, self.log = out_dir, chunk_size, k, log
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "state.json")
        self.state = {"cases": [], "intents": {}}
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.state = json.load(f)
        self.done = {r["id"] for r in self.state["cases"]}

    # persistence: state.json is the truth; stream.jsonl is rewritten from it after every case
    def save(self):
        with open(self.path + ".tmp", "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(self.path + ".tmp", self.path)
        with open(os.path.join(self.dir, "stream.jsonl.tmp"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in self.state["cases"])
        os.replace(os.path.join(self.dir, "stream.jsonl.tmp"), os.path.join(self.dir, "stream.jsonl"))

    def run_chunk(self, chunk):
        lo = (chunk - 1) * self.chunk_size
        if lo >= len(self.cases):
            raise ChunkError(f"chunk {chunk} is beyond the stream")
        if any(c["id"] not in self.done for c in self.cases[:lo]):
            raise ChunkError(f"chunk {chunk - 1} is incomplete; run it first")
        todo = [c for c in self.cases[lo:lo + self.chunk_size] if c["id"] not in self.done]
        for c in todo:
            r = self.process(c, chunk)
            self.log(f"[{chunk}] {len(self.done)}/{len(self.cases)} {c['id']} {r['intent']} {r['rung']}"
                     f"{' (fallback)' if r['fallback'] else ''} {r['answer']!r}")
        return len(todo)

    # ---- one case
    def process(self, case, chunk):
        s0 = (self.large.snap(), self.small.snap())
        intent = self.elaborate(case)
        new = intent not in self.state["intents"]
        it = self.state["intents"].setdefault(intent, {"n": 0, "labelled": [], "candidates": {"handler": None, "template": None}})
        it["n"] += 1
        pol = {kind: (c["version"] if (c := it["candidates"][kind]) and c["status"] == "active" else None)
               for kind in ("handler", "template")}
        rung, answer, fallback_from, text = self.decide_apply(case, it)
        shadow_label = False
        if rung == "large":
            self.retain_label(intent, it, case, answer, text)
        elif rung == "template" and (h := it["candidates"]["handler"]) and h["status"] == "shadow":
            # A cheaper candidate learns only from the large model's labels, so while one is in shadow the large
            # model also labels cases the template answers (bounded: it stops once the handler is promoted or
            # discarded). The case's answer stays the template's; the call is counted in its cost.
            ltext = self.large.ask(smoke.prompt(case))
            raw = smoke.extract(ltext)
            self.retain_label(intent, it, case, check(raw, case) or raw or "", ltext)
            shadow_label = True
        s1 = (self.large.snap(), self.small.snap())
        rec = {"id": case["id"], "chunk": chunk, "intent": intent, "new_intent": new, "rung": rung, "answer": answer,
               "fallback": fallback_from is not None, "fallback_from": fallback_from, "shadow_label": shadow_label,
               "large": delta(s0[0], s1[0]), "small": delta(s0[1], s1[1]), "policies": pol}
        self.state["cases"].append(rec)
        self.done.add(case["id"])
        self.save()
        return rec

    def elaborate(self, case):
        known = ", ".join(self.state["intents"]) or "(none yet)"
        text = self.small.ask(ELABORATE.format(known=known, question=case["question"]), 400)
        found = re.findall(r"Intent:\s*(.+)", text)
        return norm_key(found[-1]) if found else "unknown"

    def decide_apply(self, case, it):
        """Cheapest promoted policy, checked; the large model on a failed check. -> (rung, answer, fallback_from, large text)."""
        fallback_from = None
        for kind in ("handler", "template"):
            c = it["candidates"][kind]
            if c and c["status"] == "active":
                got, _ = self.run_candidate(c, case)
                if got is not None:
                    return kind, got, None, None
                c["fallbacks"] = c.get("fallbacks", 0) + 1
                fallback_from = kind
                break
        text = self.large.ask(smoke.prompt(case))
        raw = smoke.extract(text)
        return "large", check(raw, case) or raw or "", fallback_from, text

    def run_candidate(self, c, case):
        """-> (checked answer or None, raw answer or error text)."""
        if c["kind"] == "handler":
            raw, err = run_handler(c["code"], case)
            return check(raw, case), raw if err is None else err
        raw = smoke.extract(self.small.ask(f"Here is a plan for problems of this kind:\n{c['text']}\n\nFollow the "
                                           f"plan on the new problem.\n\n{smoke.prompt(case)}"))
        return check(raw, case), raw

    # ---- retain, shadow, compile, promote
    def retain_label(self, intent, it, case, answer, text):
        it["labelled"].append({"id": case["id"], "answer": answer, "text": text})
        for kind in ("handler", "template"):
            c = it["candidates"][kind]
            if c and c["status"] == "shadow":
                self.observe(it, kind, c, it["labelled"][-1])
        self.compile(it)

    def observe(self, it, kind, c, label):
        """Run candidate `c` on a labelled case, count the agreement, then judge it."""
        got, detail = self.run_candidate(c, self.byid[label["id"]])
        ok = got is not None and same(got, label["answer"])
        c["n"] += 1
        c["agree"] += ok
        if not ok:
            c["failures"] = (c["failures"] + [{"id": label["id"], "expected": label["answer"], "got": detail}])[-5:]
        if c["status"] == "shadow":
            if c["n"] >= MIN_PROMOTE and c["agree"] / c["n"] >= THRESHOLD:
                c["status"] = "active"
            elif c["n"] >= MIN_DISCARD and c["agree"] / c["n"] < THRESHOLD:
                c["status"] = "discarded"
                if c["rewrites"] == 0:
                    self.compile_one(it, kind, rewrite=c)

    def compile(self, it):
        for kind in ("handler", "template"):
            if it["candidates"][kind] is None and len(it["labelled"]) >= self.k:
                self.compile_one(it, kind)

    def compile_one(self, it, kind, rewrite=None):
        """Write a candidate (or rewrite a discarded one with its failures shown), then validate it on held-out labels."""
        lab = it["labelled"]
        fails = (rewrite or {}).get("failures", [])
        fcases = [self.byid[f["id"]] for f in fails[:3]]
        redo = ""
        if kind == "handler":
            used = list(rewrite["used"]) if rewrite else [r["id"] for r in lab[:3]]
            used += [c["id"] for c in fcases if c["id"] not in used]
            ex = "\n\n".join(show(self.byid[r["id"]], r["answer"]) for r in lab if r["id"] in used[:3])
            if rewrite:
                redo = ("Your earlier version gave wrong answers here (earlier code below). Fix it.\n" +
                        "\n\n".join(show(self.byid[f["id"]], f["expected"]) + f"\nYour answer: {f['got']}" for f in fails[:3]) +
                        f"\nEarlier code:\n```python\n{rewrite['code']}\n```\n")
            code = code_block(self.large.ask(HANDLER.format(examples=ex, redo=redo), 1500))
            if code:
                try:
                    compile(code, "handler", "exec")
                except SyntaxError:
                    code = None
            body = {"code": code}
        else:
            src = next((r for r in lab if r["id"] == fails[0]["id"]), lab[0]) if fails else lab[0]
            used = (list(rewrite["used"]) if rewrite else []) + [src["id"]]
            if rewrite:
                redo = (f"An earlier plan gave wrong answers on cases like these, so make this one more precise:\n"
                        + "\n".join(f"- {self.byid[f['id']]['question']} (right answer: {f['expected']})" for f in fails[:3]) + "\n")
            text = self.small.ask(TEMPLATE.format(text=src["text"], redo=redo), 500).strip()
            body = {"text": text or None}
        c = {"kind": kind, "version": (rewrite["version"] + 1) if rewrite else 1, "rewrites": 1 if rewrite else 0,
             "used": used, "n": 0, "agree": 0, "failures": [], "fallbacks": 0,
             "status": "shadow" if all(body.values()) else "discarded", **body}
        it["candidates"][kind] = c
        for r in lab:
            if c["status"] != "shadow":
                break
            if r["id"] not in used:
                self.observe(it, kind, c, r)


def build_models(a):
    return http_model(a.large_url, a.large_model, LARGE_EXTRA), http_model(a.small_url, a.small_model, SMALL_EXTRA)


def add_model_flags(ap):
    ap.add_argument("--large-url", default="http://127.0.0.1:8081")
    ap.add_argument("--large-model", default="slow")
    ap.add_argument("--small-url", default="http://127.0.0.1:8082")
    ap.add_argument("--small-model", default="fast")
    ap.add_argument("--data", default=smoke.DATA)
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--chunk-size", type=int, default=100)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chunk", type=int, required=True)
    add_model_flags(ap)
    a = ap.parse_args()
    large, small = build_models(a)
    s = Stream(a.data, a.out, large, small, a.chunk_size, a.n)
    try:
        s.run_chunk(a.chunk)
    except ChunkError as e:
        sys.exit(str(e))
    print(f"chunk {a.chunk} done: large {s.large.snap()} small {s.small.snap()}")


if __name__ == "__main__":
    main()
