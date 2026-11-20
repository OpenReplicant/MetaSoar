"""An organization as an environment: its history replayed day by day, the people and agents in it as actors that
can be interviewed (exploration) or delegated to (exploitation), and a principal whose goals it serves.

Mining (`python3 -m envkit.org mine CLONES OUT`) reads bare git clones of the org's repositories and writes one event
per line: commits with their author, co-authors and session (from commit trailers), the top-level areas touched, and
each repository's own description of itself (its README's first line). Forks keep only commits by the org's own
actors (the authors of its original repositories); the rest is counted as upstream. Author emails are not kept. The
snapshot is the org's data: it stays on the machine (`orgdata/` is ignored by git) and the declaration names it by a
variable.

The world (driver `org`): one tick a day. Outputs: `events` (that day's events, a list), `repos` (once, at the start:
each repository's description), `reply` (answers to interviews), `tick`. Input: `cmd`, a command
{"action": "interview", "params": {"who": actor, "question": text}} or {"action": "delegate", "params": {"who":
actor, "task": text}}, or {"action": "wait"}. The start event names the replay's first and last day (`day`, `until`): an agent can catch up on
the history before it acts, in the `present` days that follow it (no new history; the time to ask and delegate). Interviews go to a mailbox directory: `questions/<id>.json` for the
person to answer, `answers/<id>.json` when they have (the id is a hash of who and the question, so asking again
finds the answer). A replay runs in seconds and people answer in hours, so an answer reaches the run that asks
after it was given. Delegation is recorded, with no outcome yet: acting in the org is a later step, and the
principal's.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from envkit.core import Msg, Port, World

DAY = 86400
SEP = "\x1e"  # between fields
REC = "\x1d"  # before each commit


def _git(repo: Path, *args) -> str:
    return subprocess.run(["git", f"--git-dir={repo}", *args], capture_output=True, text=True, check=True).stdout


def mine(clones: Path, out: Path, skip=("morphogen-judge",), forks=("cognee-enhanced", "webClient-VAD-faster-whisper")):
    repos = sorted(p for p in clones.glob("*.git") if p.stem not in skip)
    fmt = SEP.join(["%H", "%at", "%an", "%s", "%(trailers:key=Co-Authored-By,valueonly,separator=|)",
                    "%(trailers:key=Claude-Session,valueonly)", "%P"])
    raw = {}
    for r in repos:
        text = _git(r, "log", "--all", f"--format={REC}{fmt}", "--name-only", "--no-renames")
        commits = []
        for chunk in text.split(REC)[1:]:
            head, _, files = chunk.partition("\n")
            sha, at, an, subj, co, sess, parents = (head.split(SEP) + [""] * 7)[:7]
            areas = sorted({f.split("/")[0] for f in files.split("\n") if f.strip()})
            commits.append({"repo": r.stem, "sha": sha[:10], "t": int(at), "author": an.strip(),
                            "coauthors": sorted({re.sub(r"\s*<.*", "", c).strip() for c in co.split("|") if c.strip()}),
                            "session": sess.strip().rsplit("/", 1)[-1] or None, "subject": subj[:200],
                            "areas": areas[:20], "merge": len(parents.split()) > 1})
        raw[r.stem] = commits
    own = {c["author"] for name, cs in raw.items() if name not in forks for c in cs}
    events, upstream = [], Counter()
    for name, cs in raw.items():
        for c in cs:
            if name in forks and c["author"] not in own:  # upstream work, even with a co-author the org also has
                upstream[name] += 1
                continue
            events.append({"kind": "merge" if c.pop("merge") else "commit", **c})
    for r in repos:
        desc = ""
        for readme in ("README.md", "readme.md", "README"):
            try:
                lines = _git(r, "show", f"HEAD:{readme}").splitlines()
            except subprocess.CalledProcessError:
                continue
            body = [ln.strip() for ln in lines if ln.strip() and not ln.startswith(("#", "!", "[", "<", "```"))]
            desc = body[0][:300] if body else ""
            break
        first = min((e["t"] for e in events if e["repo"] == r.stem), default=None)
        events.append({"kind": "repo", "repo": r.stem, "t": first or 0, "description": desc,
                       "fork": r.stem in forks, "upstream_commits": upstream[r.stem]})
    events.sort(key=lambda e: (e["t"], e["kind"] != "repo"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(e) + "\n" for e in events))
    return len(events), len(own)


def qid(who: str, question: str) -> str:
    return hashlib.sha256(f"{who}\n{question}".encode()).hexdigest()[:12]


class OrgWorld(World):
    inputs = {"cmd": Port("command", keep="all")}

    def __init__(self, name, snapshot: str, mailbox: str, principal: str = "principal", start: str | None = None,
                 end: str | None = None, present: int = 7, rate: float = 20.0):
        self.outputs = {"events": Port("event", keep="all"), "repos": Port("json", keep="all"),
                        "reply": Port("event", keep="all"), "actions": Port("event", keep="all"),
                        "tick": Port("event"), "event": Port("event", keep="all"), "reward": Port("scalar", keep="all")}
        super().__init__(name)
        if not snapshot or not Path(snapshot).exists():
            raise FileNotFoundError(f"{name}: no org snapshot at {snapshot!r} (python3 -m envkit.org mine ...)")
        self.events = [json.loads(ln) for ln in Path(snapshot).read_text().splitlines()]
        self.mailbox, self.principal, self.rate = Path(mailbox), principal, rate
        import datetime as dt
        day = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()) // DAY  # noqa: E731
        days = [e["t"] // DAY for e in self.events if e["t"]]
        self.d0 = day(start) if start else min(days)
        self.d1 = day(end) if end else max(days)
        self.i, self.asked, self.log, self.present = 0, set(), [], int(present)

    def start(self):
        for d in ("questions", "answers"):
            (self.mailbox / d).mkdir(parents=True, exist_ok=True)

    def on(self, port, msg: Msg):
        c = msg.data or {}
        a, p = c.get("action"), c.get("params") or {}
        if a == "interview":
            q = qid(p["who"], p["question"])
            self.asked.add(q)
            path = self.mailbox / "questions" / f"{q}.json"
            if not path.exists():
                path.write_text(json.dumps({"id": q, "who": p["who"], "question": p["question"],
                                            "asked_on_day": self.today, "why": p.get("why", "")}, indent=1))
            self.log.append(("interview", p["who"], p["question"]))
        elif a == "delegate":
            self.log.append(("delegate", p["who"], p.get("task")))

    def _replies(self):
        out = []
        for q in sorted(self.asked):
            a = self.mailbox / "answers" / f"{q}.json"
            if a.exists():
                out.append({"id": q, **json.loads(a.read_text())})
                self.asked.discard(q)
        return out

    def tick(self, t: int):
        self.today = self.d0 + t
        if t == 0:
            self.emit("actions", {"names": ["wait", "interview", "delegate"], "points": [False, False, False]})
            self.emit("event", {"kind": "start", "day": self.today, "until": self.d1})
            self.emit("repos", [e for e in self.events if e["kind"] == "repo"])
            # answers given since an earlier run: every question already in the mailbox, answered
            for a in sorted((self.mailbox / "answers").glob("*.json")):
                self.asked.add(a.stem)
        today = []
        while self.i < len(self.events) and self.events[self.i]["t"] // DAY <= self.today:
            e = self.events[self.i]
            if e["kind"] != "repo":
                today.append(e)
            self.i += 1
        self.emit("events", today)
        for r in self._replies():
            self.emit("reply", r)
        self.emit("reward", 0.0)
        self.emit("tick", {"day": self.today})
        if self.today >= self.d1 + self.present:  # the history, then a few days of the present to act in
            self.done = True
            self.emit("event", {"kind": "end", "steps": t, "interviews": sum(1 for x in self.log if x[0] == "interview")})


# --- adapters into the workspace: entity resolution, mechanical and fair ----------------------------------------


def resolve(events, t):
    """Each day's events: an entry per event (gone the next day) and the actors and repositories they touch, with
    running counts (the mechanical part of the map; what they mean is the cartographer's)."""
    out = []
    for e in events:
        if e["kind"] not in ("commit", "merge"):
            continue
        out.append({"key": f"commit:{e['repo']}:{e['sha']}", "kind": "commit", "ttl": 1, "attrs": e})
        for who, role in [(e["author"], "author")] + [(c, "coauthor") for c in e["coauthors"]]:
            out.append({"key": f"actor:{who}", "kind": "actor",
                        "attrs": {"last_day": e["t"] // DAY, f"last_{role}_repo": e["repo"]}})
    return out


def repos(data, t):
    return [{"key": f"repo:{r['repo']}", "kind": "repo",
             "attrs": {"description": r["description"], "fork": r["fork"], "upstream_commits": r["upstream_commits"]}}
            for r in data]


def reply(data, t):
    return [{"key": f"reply:{data['id']}", "kind": "reply", "salience": 1.0, "attrs": data}]


def main(argv=None):
    a = argv or sys.argv[1:]
    if a and a[0] == "mine":
        n, own = mine(Path(a[1]), Path(a[2]))
        print(f"{n} events, {own} of the org's own actors")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
