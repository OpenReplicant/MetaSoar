"""Checks that need no game: python3 -m envkit.test_envkit (or pytest)."""
from __future__ import annotations

from envkit.core import Environment, Lockstep, Module, Port, World, attach


class W(World):
    outputs = {"frame": Port("grid16"), "ram": Port("json", fair=False), "extra": Port("json"),
               "tick": Port("event")}
    inputs = {"cmd": Port("command")}

    def __init__(self, name, ticks=3):
        super().__init__(name)
        self.ticks, self.got = ticks, []

    def on(self, port, msg):
        self.got.append(msg.data)

    def tick(self, t):
        self.emit("frame", t)
        self.emit("tick", t)
        self.done = t + 1 >= self.ticks


class A(Module):
    kind = "agent"

    def __init__(self, name):
        self.inputs = {"x": Port("json"), "tick": Port("event")}
        self.outputs = {"cmd": Port("command")}
        super().__init__(name)
        self.seen, self.acted = None, []

    def on(self, port, msg):
        if port == "x":
            self.seen = msg.data
        else:
            self.acted.append(self.seen)
            self.emit("cmd", self.seen)


class Double(Module):
    kind = "encoder"
    inputs = {"in": Port("json")}
    outputs = {"out": Port("json")}

    def on(self, port, msg):
        self.emit("out", msg.data * 2)


def env(*extra):
    return Environment("t", [W("game"), *extra],
                       expose={"frame": "game.frame", "ram": "game.ram", "extra": "game.extra", "cmd": "game.cmd",
                               "tick": "game.tick", "double": "enc.out"},
                       profiles={"judged": ["frame", "ram", "tick", "double"], "train": ["frame", "ram", "extra",
                                                                                         "tick", "double"]})


def test_fairness():
    """An agent may read what its profile lists and the world marks fair; anything, with no profile."""
    want = {("frame", "judged"): True, ("ram", "judged"): False, ("extra", "judged"): False,
            ("extra", "train"): True, ("ram", "train"): False, ("ram", None): True}
    for (exposed, profile), ok in want.items():
        try:
            attach(env(), A("a"), {"x": exposed, "cmd": "cmd"}, profile=profile)
            got = True
        except PermissionError:
            got = False
        assert got == ok, (exposed, profile, got)


def test_taps_are_not_judged():
    t = A("t")
    t.kind = "tap"
    attach(env(), t, {"x": "ram"}, profile="judged")


def test_encoder_output_reaches_agent_before_tick():
    """Depth first: the world's frame goes through the encoder and reaches the agent before the world's tick."""
    enc = Double("enc")
    e = env(enc)
    enc.wired_in["in"] = "game.frame"
    a = A("a")
    attach(e, a, {"x": "double", "tick": "tick", "cmd": "cmd"}, profile="judged")
    Lockstep(e.modules + [a]).run()
    assert a.acted == [0, 2, 4], a.acted
    assert e.modules[0].got == [0, 2, 4]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
