# Changes for the Knowledge Kernel, made here

Work on `OpenReplicant/kernel` done from MetaSoar, kept as patches until it goes to the kernel as pull requests.
Each is a `git format-patch` against the kernel's `main` at the commit named below, tested with the kernel's own
checks (`kernel/schema/tests/run.sh`, `scripts/smoke_kernel.sh`).

    git -C path/to/kernel am patches/kernel/0001-*.patch

| patch | base | what | checked |
|---|---|---|---|
| 0001 | efbdec2 | kernel-mcp: `search` and `recall` work on Postgres without pgvector again (a guard query named a table that may not exist) | 30 kernel checks; the smoke test in full on Postgres 16, with pgvector and without it |
