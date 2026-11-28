"""Reference-aware project check. PM-1a's score.py finds the project a reply concerns only from tool arguments or the
literal project id in the reply text; a correct reply that says "w-31", "PR 34", "claude/e19", "d-2" or "E-19" names no
project to it. `rescore` takes score.score's dict and, when its project check failed, adds the projects those references
stand for (read off the live portfolio at that turn) to the named set and recomputes project_ok and routing_ok the way
score.py does. score.py itself is not touched; the raw verdict stays in `project_ok_raw`.

A reference maps to a project only when it is unambiguous: worker ids, branches, decision ids (of a decision with a
project) and PR numbers belong to one project's records; an experiment or knowledge id (E-19, S-170 ...) only if it
appears in exactly one project's text (goal, status, next step, notes, PR titles, worker briefs, decisions, knowledge).
"""
from __future__ import annotations

import re

READ_TOOLS = ("pm_portfolio", "kernel_search")  # a read names what it looked at, not what the reply concerns
_ID = re.compile(r"(?<![\w-])([A-Z]{1,4}-\d+[a-z]?)(?![\w-])")  # E-19, E-17d, S-170 (case-sensitive: not w-21, d-2)
_WORKER = re.compile(r"(?<![\w-])(w-\d+)(?![\w-])", re.I)
_DECISION = re.compile(r"(?<![\w-])(d-\d+)(?![\w-])", re.I)
_PR_LIST = re.compile(r"(?<![\w])(?:PRs?|pull\s+requests?)\s*#?\d+(?:\s*(?:,|and|&|/)\s*#?\d+)*", re.I)
_PR_HASH = re.compile(r"(?<![\w&/])#(\d+)\b")


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)


def _prs(text):
    out = set()
    for m in _PR_LIST.finditer(text):
        out |= set(re.findall(r"\d+", m.group(0)))
    out |= set(_PR_HASH.findall(text))
    return out


def _lit(token):
    return re.compile(rf"(?<![\w/.-]){re.escape(token)}(?![\w-])", re.I)


class RefMap:
    """reference -> project, for one moment of a day (or one episode)."""

    def __init__(self, portfolio: dict, hints: dict | None = None):
        self.workers, self.decisions, self.branches, self.prs, self.ids = {}, {}, {}, {}, {}
        texts: dict[str, list[str]] = {p["id"]: [] for p in portfolio.get("projects", [])}
        seen_prs: dict[str, set] = {}

        def text_of(pid, *parts):
            texts.setdefault(pid, []).extend(str(x) for x in parts if x)

        for p in portfolio.get("projects", []):
            pid = p["id"]
            text_of(pid, p.get("goal"), p.get("status"), p.get("next_step"), *(p.get("notes") or []))
            for pr in p.get("prs") or []:
                seen_prs.setdefault(str(pr.get("number")), set()).add(pid)
                text_of(pid, pr.get("title"))
        for w in portfolio.get("workers", []):
            if w.get("project"):
                self.workers[w["id"].lower()] = w["project"]
                text_of(w["project"], w.get("brief"))
                if w.get("branch"):
                    self.branches[w["branch"]] = w["project"]
        for d in portfolio.get("decisions", []):
            if d.get("project"):
                self.decisions[str(d["id"]).lower()] = d["project"]
                text_of(d["project"], d.get("text"))
        for k in portfolio.get("knowledge", []):
            if k.get("project"):
                text_of(k["project"], k.get("id"), k.get("text"))
        for tok, pid in (hints or {}).items():  # worker ids and branches/paths the day knows (started workers, event refs)
            if re.fullmatch(r"w-\d+", tok, re.I):
                self.workers.setdefault(tok.lower(), pid)
            else:
                self.branches.setdefault(tok, pid)
        ids: dict[str, set] = {}
        for pid, parts in texts.items():
            blob = " ".join(parts)
            for t in _ID.findall(blob):
                ids.setdefault(t, set()).add(pid)
            for n in _prs(blob):
                seen_prs.setdefault(n, set()).add(pid)
        self.prs = {n: next(iter(s)) for n, s in seen_prs.items() if len(s) == 1}
        self.ids = {t: next(iter(s)) for t, s in ids.items() if len(s) == 1}
        # a branch name shared by two projects is no reference
        self._branch_res = [(_lit(b), pid) for b, pid in self.branches.items()]

    def find(self, text: str) -> dict:
        """{reference: project} for every mapped reference in the text."""
        out = {}
        for m in _WORKER.finditer(text):
            if m.group(1).lower() in self.workers:
                out[m.group(1).lower()] = self.workers[m.group(1).lower()]
        for m in _DECISION.finditer(text):
            if m.group(1).lower() in self.decisions:
                out[m.group(1).lower()] = self.decisions[m.group(1).lower()]
        for n in _prs(text):
            if n in self.prs:
                out[f"PR {n}"] = self.prs[n]
        for t in _ID.findall(text):
            if t in self.ids:
                out[t] = self.ids[t]
        for rx, pid in self._branch_res:
            m = rx.search(text)
            if m:
                out[m.group(0)] = pid
        return out


def turn_texts(sc: dict, trace: list, final_text: str) -> list:
    """What the turn said and sent: every string argument of a successful tool call (not the read tools), and the closing
    text when it is a reply to a person (a supervisor event has no one to forward it to)."""
    out = []
    for c in trace:
        if "tool" in c and not c.get("error") and c["tool"] not in READ_TOOLS:
            out.extend(_strings(c.get("arguments")))
    if "event" not in sc and (final_text or "").strip():
        out.append(final_text)
    return out


def rescore(score: dict, sc: dict, portfolio: dict, trace: list, final_text: str, hints: dict | None = None) -> dict:
    """score.score's dict plus `named_refs` (the projects the turn's references stand for) and `project_ok_raw` (score.py's
    verdict). When the raw project check is False, `named` becomes score's set plus those projects, `project_ok` is
    named == {expected} and `routing_ok` is action_ok and project_ok is not False. An unscored project (None) stays None."""
    exp = sc["expected"]
    out = dict(score)
    rm = RefMap(portfolio, hints)
    found = {}
    for t in turn_texts(sc, trace, final_text):
        found.update(rm.find(t))
    out["named_refs"] = sorted(set(found.values()))
    out["named_ref_hits"] = found
    out["project_ok_raw"] = score["project_ok"]
    if score["project_ok"] is False:
        named = set(score["named"]) | set(found.values())
        out["named"] = sorted(named)
        out["project_ok"] = named == {exp["project"]}
        out["routing_ok"] = bool(score["action_ok"] and out["project_ok"] is not False)
    return out
