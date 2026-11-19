# envkit: pluggable environments

An environment here is declared, not written: a file names its modules and how they are wired, and the same
agent runs in an ARC-AGI-3 game, a NES game, a Doom map or a live stream with a game inside it without code
written for any of them. It follows Substrate's environment contract (`docs/archive/contracts/environment.md`,
S-101, S-102: the environment is the unit that is configured, started and shared; environments nest) and adds
what playing live needs: time, rates, and taking the agent's attention into account.

## The pieces

- **Module**: an actor. It has a name, ports it reads and ports it writes, and no shared state: it acts only on
  the messages delivered to it and only by emitting messages. Kinds, by what they do:
  - a **world** steps something outside the agent (a game, an emulator, a chat): it reads commands and writes
    readings;
  - an **encoder** turns readings into other readings (a frame into objects, depth into obstacles);
  - an **agent** reads readings and writes commands;
  - a **tap** only reads (a recorder, a viewer, a stream encoder); nothing it does can change a run.
- **Channel**: a named stream of messages. A message is `(channel, t, seq, source, data)`: `t` is the
  environment's clock (ticks), `seq` orders messages within a tick, `data` is the payload.
- **Port**: a module's end of a channel, with a type (`grid16`, `rgb`, `depth`, `labels`, `scalar`, `text`,
  `command`, `event`) and a keep policy: `latest` (only the newest message matters: a frame) or `all` (every
  message matters: chat lines, events).
- **Environment**: a set of modules and their wiring, itself a module. It exposes some of its channels as its own
  ports, so a stream environment can hold a game environment as one of its modules (nesting).
- **Declaration**: a TOML file, data only. Drivers (the code that runs a world: `gym`, `nes`, `vizdoom`) are
  looked up by name in a registry; parameters fill in seeds, levels and paths (a ROM's path comes from the
  machine, never from the repository).

## Custody (who may change what)

As in Substrate's contract: the **world** side (drivers, the readings offered, actions and their gate, the
outcome) is changed by people; the **agent** side (its encoders, how it chooses, its local models) is where
candidates change things; the **scorer** is the judge's. A declaration marks each reading **fair** or not for a
profile: ViZDoom's per-pixel labels are privileged (a person playing does not see them), so a judged profile
offers only the screen. The agent reconfigures itself within what the profile offers, never beyond it.

## Time: one set of modules, two schedulers

The scheduler is separate from the modules, so the same modules run both ways:

- **Lockstep** (training, judging, fast runs): each tick, every world emits its readings; messages are delivered
  depth first until nothing more is emitted (what a module emits while handling a message goes before the next
  queued message, so an encoder's output reaches the agent before the world's tick; every agent has answered); then the clock advances and each world steps with the
  latest command it has (or its declared no-op). Deterministic for a seed, and as fast as the computer allows.
- **Realtime** (watching, streaming, people in the loop): each world steps at its declared rate on the wall clock
  with whatever command is latest; agents run concurrently and may be late. A slow path (a model call) cannot hold
  the game up; something fast has to keep playing meanwhile. That is the fast and slow design made necessary
  rather than chosen.

## Drivers and taps so far

| name | what | file |
|---|---|---|
| `gym` | any Gymnasium environment (the ARC-AGI-3 games through `metasoar.envs`) | `modules.py` |
| `nes` | a NES cartridge through nes-py: buttons, the title-screen sequence, memory readings by address, lives and levels as fair counts | `nes.py` |
| `quantize` | an encoder: an RGB screen to a grid of up to 16 colour indices, block by block | `nes.py` |
| `chat` | a scripted audience | `modules.py` |
| `Film`, `Live` | taps: the screen with the agent's reasons beside it, as a GIF (`--film`) or served live on 127.0.0.1 (`--live PORT`, an MJPEG page a browser or OBS can show) | `watch.py` |

Declarations: `environments/arc3.toml`, `environments/mario.toml` (Super Mario Bros.), `environments/stream.toml`
(a game plus a chat). ROMs are the owner's: a declaration reads the path from `NES_ROM`, `*.nes` is ignored by git,
and no image contains one.

    NES_ROM=~/roms/smb.nes python3 -m envkit.run mario --realtime --live 8765     # then open http://127.0.0.1:8765
    NES_ROM=~/roms/smb.nes python3 -m envkit.run mario --param max_steps=3000 --film run.gif

nes-py needs `pip install nes-py` (it builds a small C++ extension; wheels exist for Python 3.13 on Linux). Hacks
of a cartridge on mappers 0 to 3 run if their memory map matches the declaration; one that moves the player's
position or lives elsewhere needs its own declaration.

### First runs on Mario (1-1, frameskip 4, seed 0)

| agent | steps | progress (pixels) | lives lost | end |
|---|---|---|---|---|
| atlas (claims from ARC, no Mario knowledge) | 3000 | 1620 | 1 (the timer, stuck at the third pipe) | step limit |
| fixed: hold right, jump 8 steps in 16 | 553 | 2093 | 3 | game over |

The atlas moves right and jumps the first pipes but stalls where a pipe is taller than one jump from a walk,
until the clock runs out. A fixed rule gets further, faster. The atlas's ideas (objects, contact, claims) were made
for still grids where nothing moves unless the agent does; a platformer has gravity, momentum, enemies that move
on their own and a camera that scrolls, so its first job is to tell its own motion from the world's.

## Why actors

Nesting, mixed rates (a game at 60 steps a second, chat at a line every few seconds, a model answering in
seconds) and attention (what to read now) all come out of modules that only exchange messages. The mailbox is a
narrow interface (`publish`, `subscribe`), so the in-process bus here can be replaced later by queues in
Postgres (pgmq) with each actor its own process under a process manager, as Substrate planned, without changing a
module. Until a second process is needed it stays in process.

## What this does not decide

How an agent assesses its situation and reconfigures itself (which encoder, which local models, when to call a
model, how to split attention between a game and an audience): that is the agent's, built on these pieces, and
judged like any other agent code.
