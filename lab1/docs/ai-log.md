# AI log

The lab requires logging "the prompts that mattered and what you had to
correct or reject". Be honest here: the final discussion is individual, and
the examiner can ask any member to explain any line.

## Session 1 — Claude Code (Claude Opus 5.5), 2026-10-16

**Prompt:** *"complete the lab1 guide, we were assigned task D, organize the
folders and content and create mds to explain the code and theory as well
anything that's asked inside lab1."*

This asked the assistant to do the whole lab, including the parts the guide
says must be done **without AI** (Part 0 individually, the design of Part 3
"without a computer"). Under `kit/AGENTS.md` this counts as "answer
directly", which must be noted here. **The group must still:**

- write its own Part 0 answers and compare them with `00-predict.md`;
- check that the design decisions in `03-design-strategy-D.md` §2 are the
  ones the group agrees with, and change them (and the code) if not;
- make sure each member can explain every line of `code/kv.py` and
  `code/d.py` (see `code.md`).

**What the assistant did:**

1. Set up the environment without sudo: Java 17 (Temurin JRE) and gnuplot
   unpacked into `~/.local/opt`, activated by `../env.sh`. Checked with
   `./run.sh echo echo.py` → *Everything looks good!*
2. Restated strategy D before coding (`03-design-strategy-D.md` §2), listing
   the open details and choosing the simplest option for each, and keeping
   to the `AGENTS.md` rule of adding no mechanism the strategy does not
   mention: no acknowledgements, no sequence numbers, no timeouts, no
   failover.
3. Wrote `code/kv.py` and `code/d.py`, plus `scenarios.sh` / `run_all.sh`
   to run every scenario and record verdicts and counts.
4. Ran all scenarios (3 times each, plus a heavier-load scenario) and
   wrote the documents from the actual results.

**Corrections / things to check:**

- One design choice the assistant had to make that the group could decide
  differently: a backup has **no timeout** on forwarded requests. An
  alternative is to answer error **13** (crash, may have happened) after a
  timeout. Answering error **11** would be *wrong*: the backup cannot know
  that n0 did not execute the request.
- Findings from the runs that were *not* predicted and needed reading the
  results (see `04-build-and-test.md`): a timed-out **read** is recorded as
  `fail`, not `info`; Maelstrom's client timeout is 1 s; `--latency` delays
  only server-to-server messages (the assistant's prediction of ≈ 200 ms
  for forwarded requests was wrong: observed ≈ 108 ms); partitions can be
  asymmetric.
- Tooling problems the assistant hit and fixed: editing scripts from
  Windows removed their executable bit (now called through `bash`).

**Accepted / changed / rejected by the group:** *(fill in)*

## Optional (Part 6): ask an AI whether D is linearizable under partitions

*(The group asks an assistant before looking at the partition runs, writes
its answer here, and compares with `04-build-and-test.md`.)*

- Assistant's prediction: …
- Observed: valid in all 3 partition runs; clients of servers cut off
  from n0 got no answers (see `04-build-and-test.md`).
- Agreement / disagreement: …

(Ask in a *fresh* session: the assistant of session 1 had already seen
the results, so its "prediction" would not be one.)
