# RETROSPECTIVE.md — what this project got wrong, and how to set up the next one

> **Who this is for.** Written for a data scientist who is strong on method and light on software
> engineering. Every term of art is explained the first time it appears, in a plain-language box.
> Nothing here assumes you have shipped production software before.
>
> **Scope.** The whole project, not just the re-ingest: the gold-set / measurement phase (P0-9) and
> the re-ingest phase (P1). Each item is something that actually happened, evidenced in
> `HANDOFF.md`, `IMPROVEMENTS.md` and `logs/` — not a generic best-practice list.
>
> **How to use it.** Section 1 is the short version. Sections 2–6 are the failures grouped by theme,
> each as *what happened → why it was possible → what would have caught it*. Section 7 is a concrete
> opening system prompt you can paste into the next project. Section 8 is a one-page checklist.

---

## 1. The short version

The engineering in this project is not the problem. The **measuring instruments** were built after
the thing they measure, and the **failure handling** was designed for the happy path.

Three sentences that would have saved most of the time spent:

1. **Build the ruler before the thing you want to measure.** The gold dataset (the labelled set of
   questions and correct pages) is the ruler. It was assembled *after* the retrieval pipeline, so
   every early number was measured with a ruler of unknown length — and several conclusions turned
   out to be unresolvable, not because the pipeline was good or bad but because the ruler was too
   coarse.
2. **For any job that runs for an hour, decide up front how much work you are willing to lose.**
   Three runs of the re-ingest each threw away 86, 53.6 and 63.8 minutes of finished work, because
   the pipeline computes everything in memory and writes once at the end. Retrying reduces how
   *often* it fails. Only a checkpoint reduces how *much* a failure costs.
3. **A test that has never been seen to fail is a guess, not a guarantee.** Three separate tests in
   this project passed while proving nothing about the real system. Each was written with good
   intent and each measured the test's own scaffolding rather than the code.

---

## 2. Scoping: the project was defined by what to build, not by what to prove

### 2.1 The success criterion arrived after the architecture

**What happened.** The project began as "build a hybrid RAG platform" — a list of components
(parser, chunker, embedder, vector store, re-ranker, graph, cards, UI). Metrics entered late, as
P0 ("make the numbers trustworthy"), by which point the components were fixed and the numbers
they produced could not be trusted.

**Why it was possible.** "Build X" is a buildable goal, so work could always continue. "Prove X
improves Y by Z" is not buildable, so it forces uncomfortable early decisions.

**What would have caught it.** Writing the *result* you want as a sentence with a number and a
comparison in it, before any component exists. For this project that sentence is roughly:

> *"A student question about Feynman Vol I returns the page that answers it in the top 5 results,
> at least 80% of the time, and the system says 'I don't know' when the answer is not in the book."*

Every architectural choice can then be tested against that sentence. Note that the sentence names
a **unit** (the page), a **metric** (top-5 hit rate), a **threshold** (80%) and a **negative case**
(abstention). Without those four, you cannot tell improvement from noise — which is exactly the
state the project was in for its first two phases.

> **Metric.** A number you compute to judge the system. **Recall@20** = of all the pages that
> actually answer a question, what fraction appear in the 20 results returned. **Unit** = the thing
> being counted (a page, a chunk, a document). Getting the unit wrong makes the metric meaningless
> no matter how carefully it is computed.

### 2.2 The gold dataset — the ruler — was built last

**What happened.** The evaluation set (questions + which pages answer them) was assembled in
Sessions 1–4, *after* the pipeline. Its first version had a fatal property: early labels were
derived from what the retriever returned, so the evaluation was circular — the system was being
graded on its own homework. That version was discarded (`D6`), and everything measured with it
became non-comparable.

**Why it was possible.** Building a labelled dataset is slow, unglamorous and has no visible
output. Building a chunker has visible output immediately.

**What would have caught it.** Treat the evaluation set as the **first** deliverable, not the last,
and build it from a source the system never touches — here, reading the book. The project did
eventually reach exactly this discipline (a VLM reading page *images* as an independent judge, an
independent PDF text extractor to verify page numbers), and those are the parts that held up.

> **Circular evaluation.** Judging a system using information that came from the system. It always
> looks like it is working, because the answers are already in the questions. The tell: your
> accuracy is suspiciously high and falls apart the moment you test on new data.

### 2.3 "How many samples do I need?" was asked after collecting them

**What happened.** Five separate questions — does the re-ranker help, is ColBERT better as a voter
or a judge, did a bug-fix help, is abstention any good, does anything differ by question type —
were all answered at n=23 queries and **all five were unresolvable**: the confidence intervals were
wider than any effect worth detecting. The measured statistical noise (σ_d = 0.2315) implied **62
queries to detect the effect actually observed**, and the project had 23.

**Why it was possible.** Running an experiment is easy; working out in advance how much data it
needs is not, and nobody enjoys doing it.

**What would have caught it.** A **power calculation before collecting**: given the noise in your
measurement and the smallest effect you care about, how many samples do you need? It is one
formula (`N ≈ 0.42/δ²` in this case) and it takes ten minutes. The project did eventually do this
(`required_n.py`) and it was right — the point is that doing it first would have prevented two
rounds of experiments whose answers could not be used.

> **Power.** The number of samples needed to tell a real effect from luck. **Confidence interval
> (CI)** = the range of values consistent with your data. If the CI spans zero, you cannot claim an
> effect — that is "unresolved", which is a legitimate result but a useless one to have spent weeks on.

### 2.4 Scope decisions were made late and then held

**What happened.** Single-user versus multi-tenant was settled only after the architecture existed.
The plumbing for multi-tenancy was built, then deliberately not enforced, then frozen ("do not add
new `tenant_id` defaults").

**Why it was possible.** The decision had no deadline and no owner, so it drifted.

**What would have caught it.** A one-page scope statement with explicit **non-goals**, agreed before
code. "Multi-tenancy: not now, not until retrieval metrics are solid" is a perfectly good decision —
but it needs to be written down on day one so that work can be refused against it, rather than
discovered halfway through.

---

## 3. Planning: the plan was excellent and still missed the environment

### 3.1 The plan assumed the cluster would be available and stable

**What happened.** The re-ingest plan is genuinely good: ten steps, closed decisions, risks with
mitigations. It estimates the run at "tens of minutes" for parsing and ~48 minutes for embedding.
What it does not contain is any treatment of the embedding service being **shared, contended and
intermittently unreachable**. It was all three. Three runs failed against it.

**Why it was possible.** The plan was written from the code's perspective (what has to change)
rather than the run's perspective (what has to survive). Every estimate was a happy-path estimate.

**What would have caught it.** For any dependency you do not control, ask three questions and write
the answers down: *who else uses it, how does it fail, and what does my job do when it does?* Here
the answers were "other students, by becoming unreachable for minutes at a time, and it threw away
everything" — the third answer is the one that cost 3.5 hours.

### 3.2 The plan's verification steps were count checks, not property checks

**What happened.** The plan's stated verification for the run was "collection points == SQLite
chunks; dims correct". That check **passes on a broken index**: the code that writes the optional
vector lanes (SPLADE, ColBERT) wraps them in a `try/except` that logs a warning and continues, so a
collection can be missing two of its four vector lanes, have the right number of points, and look
completely healthy (`§I15`).

**Why it was possible.** Counts are the easiest thing to check, so they became the definition of
"verified".

**What would have caught it.** Asking what the check would look like **if the thing were broken**.
"Points == chunks" cannot detect a missing lane, so it is not a check for that failure. The
replacement — scroll every point, count how many carry each lane, fail if any lane is missing from
any point — is barely more code and actually detects it.

> **Property check.** A check on *how* something is, not *how many* of it there are. "There are 3,796
> rows" is a count. "Every row has all four vector lanes" is a property. Broken systems usually keep
> the counts right.

### 3.3 The plan did not say how to tell whether it had worked

**What happened.** Step 10 ("re-measure") is one line. The re-ingest changes chunk boundaries,
embeddings, page numbers and the collection schema — so "did it work?" needs an explicit
before/after comparison with a pre-declared threshold. That was not written down in advance, which
means it will be decided after seeing the numbers.

**Why it was possible.** The measurement plan lived in a different document (the P0-9
pre-registration) and was not carried into the re-ingest plan.

**What would have caught it.** Every plan ends with the same paragraph: *"This phase is done when
<metric> moves from <before> to <after>, measured by <command>, and here is what I will conclude if
it does not."* Written before running anything.

> **Pre-registration.** Writing down in advance what result would change your mind. It is the only
> defence against the very human habit of looking at a number and deciding afterwards that it is
> fine.

---

## 4. Verification: three tests that passed while proving nothing

This is the single most useful section. All three happened in one session, in code written
carefully, by someone actively looking for this exact failure.

### 4.1 The deadline test that never exercised the deadline

**What happened.** A test was written to prove that a slow, trickling network response is cut off
after a time limit. It passed. It proved nothing: the test's own helper fixture patched
`time.sleep` **globally** (not just inside the module under test), so the "slow" response never
actually slept. The test asserted a limit that was never approached.

**Why it was possible.** The fixture looked correct. The bug was invisible in the test file — it was
in a shared fixture that had been fine for every previous test.

**What would have caught it.** Running the test against a version of the code with the feature
*removed* and confirming it fails. The project now does this deliberately, and did it for the cache
fix: temporarily restore the bug, watch the test fail, then fix. That is the only way to know a test
is load-bearing.

### 4.2 The cache test that cheated without meaning to

**What happened.** A new resume-cache (see §5.2) validated its stored data by comparing chunk
identifiers. Those identifiers are randomly generated fresh on every run — so in production the
cache could **never** have returned a hit. It would have looked healthy: files written, no errors,
zero benefit. The test passed because it handed the *same* objects to both passes, so the random
identifiers happened to match.

**Why it was possible.** The test was written by someone who knew the objects were reused — the
knowledge was in the author's head and not in the test.

**What would have caught it.** A test that constructs its inputs **the way the production code
does**. Here: same text, same positions, brand-new identifiers. The project now has that test, and
it was verified to fail against the broken version.

### 4.3 The test that was flaky and read as strict

**What happened.** A test asserted that retry delays strictly increase. They are deliberately
randomised ("jitter") so that many clients do not retry in lockstep — so the assertion is not
merely flaky, it is wrong. It passed several times, then failed.

**Why it was possible.** Strict-looking assertions feel like stronger tests.

**What would have caught it.** Asserting the property that is actually guaranteed (the *base* delay
doubles; each draw is within a stated range) rather than one that merely looked nice. A test that
fails randomly is worse than no test, because it teaches people to re-run rather than investigate.

### 4.4 The independent reviewer returned "pass" in 19 seconds

**What happened.** Two diffs were sent to a *different* AI model for independent review, with the
evidence embedded. Both came back `passed: true` with no findings — after **one** API call and
**19 seconds** each, for 200-line diffs with seven specific technical questions attached. That is a
read-and-agree response, not a review.

**Why it was possible.** An LLM asked "is this correct?" will often say yes. Its agreement costs
nothing and looks like verification.

**What would have caught it.** Treating a clean, fast pass as **no signal** rather than a green
light — and then checking the reviewer's specific claims yourself. When this was done, one
reviewer's finding turned out to be **false** (it had misread a line's bracketing, claiming a crash
that provably does not occur) and another was **right for the wrong reason** (it flagged a threading
concern; the real hazard was elsewhere in the same function, and it was real). So: the reviewer was
useful, but only after adjudication — and the "pass" verdicts were not evidence of anything.

**The rule this suggests.** An independent check is a **filter, not a proof**. Use it to generate
candidate defects, then verify each one against the running code. Record which claims were false —
that is how you learn what your reviewer is bad at.

---

## 5. Failure handling: the system was designed for the happy path

### 5.1 No retry: one bad network read cost 86 minutes

**What happened.** The embedding client made one HTTP request per section of the book and had **no
retry**. A single timeout — on a service that was demonstrably healthy moments later — aborted the
run. 260 of 341 sections were already finished. All of it was discarded.

**Why it was possible.** The code was correct for a reliable network. It was never asked what
should happen on an unreliable one.

**What would have caught it.** For any network call in a long job: assume it *will* fail
occasionally, and decide what happens. The distinction that matters is between failures that might
succeed if repeated (timeouts, connection errors, "server busy") and failures that will not (a
malformed request). Retry the first, fail fast on the second.

### 5.2 No checkpoint: the fix for §5.1 was not enough

**What happened.** With retry in place, the second run failed differently — the service became
unreachable for 22 minutes and stayed down. The retry worked perfectly (600 attempts instead of
dying at the first timeout) and the run was still lost, because a genuinely dead service cannot be
retried into existence.

**Why it was possible.** Retry was chosen because it was the obvious fix, and "the obvious fix" is
rarely evaluated against *how much the failure costs*.

**What would have caught it.** Asking the two questions separately:
- *How do I make failure less likely?* → retry, timeouts, health checks.
- *How do I make failure cheaper?* → a checkpoint: save the finished work as you go, so a re-run
  only does what is missing.

The second question was not asked until three runs had been lost. The resulting cache (§4.2) means
the next re-run needs only the missing sections instead of all 341.

> **Checkpoint.** A saved marker of progress, so an interrupted job can resume rather than restart.
> **Idempotent.** An operation that can be repeated without changing the outcome — the property that
> makes retrying and resuming safe.

### 5.3 A timeout that did not bound the time

**What happened.** The client set a 120-second "read timeout". It did not work the way everyone
assumed: the limit applies to each individual read of the network stream, not to the request as a
whole. A response that trickles data steadily resets the clock on every fragment, so the request can
run for **21.5 minutes in total** without ever tripping a 120-second limit. The log went silent for
those 21.5 minutes and no error was raised, so the retry logic had nothing to react to.

**Why it was possible.** The setting has a reassuring name. Nobody re-derived what it actually
measures.

**What would have caught it.** Distinguishing a *per-operation* timeout from a *total deadline*, and
having both. The fix reads the response in pieces and checks a wall clock against a total budget.

### 5.4 Silent fallbacks in the write path

**What happened.** Two of the four vector lanes are written inside `try/except` blocks that log a
warning and carry on. If either fails, the ingest **succeeds** and writes an index missing those
lanes — and every count-based check passes (`§I15`). Retrieval then quietly loses its hybrid-search
capability, with no error anywhere.

**Why it was possible.** Each `try/except` was added to make an optional feature non-fatal, which is
a reasonable local decision. The problem is that "optional feature" and "silently incomplete data"
are the same code path.

**What would have caught it.** A rule: **a fallback that changes the meaning of stored data must be
loud or absent.** Either fail the write, or record the degradation in the output where a reader will
see it. The project has an earlier, related instance of the same class — an embedding failure that
substituted zero vectors (`§I9`) — which suggests this is a recurring pattern worth a standing rule
rather than a one-off fix.

> **Silent fallback.** When code hits a problem and quietly does something else instead of failing.
> It is the most dangerous kind of bug, because the system reports success. The tell: a `try/except`
> whose `except` branch does not raise, return an error, or mark the output.

### 5.5 A test proving the environment, not the code

**What happened.** Attempt 3 of the run was launched believing it would use 4 parallel workers. It
used 8. The configuration default had been changed to 4, but a `.env` file (a local settings file)
still pinned 8, and a `.env` value overrides a code default. Nothing printed which value was in
force, so the mistake was only discovered afterwards, from the logs.

**Why it was possible.** Two sources of truth for the same setting, and no assertion that they agree.

**What would have caught it.** Printing the **resolved** configuration at launch and asserting the
values you intend. The run script now does exactly this, and the first thing attempt 4 printed was:

```
RESOLVED SETTINGS (what this run will actually use)
  late_chunk_workers = 4
  embed_cache        = True -> ./data/embed_cache
```

> **Resolved configuration.** The values the program actually ends up using after defaults, config
> files and environment variables have all been applied — which is often not the value you set.

---

## 6. Measurement discipline: probes that did not represent production

### 6.1 A performance probe with one payload size

**What happened.** Before parallelising the embedding calls, a probe measured throughput at 1, 2, 4,
8 and 16 concurrent requests. It used a **fixed 1,749-token** payload. Real sections range from 13 to
4,762 tokens (median 1,190). The probe concluded "no collapse up to 16 workers" — but it had never
tested the size regime the real job runs in. Eight workers then helped knock the service over.

**Why it was possible.** A probe needs *a* payload; picking the middle one feels neutral.

**What would have caught it.** Sweeping the axes that matter — concurrency **and** payload size — or
at minimum using the real distribution's high percentile. A probe validates a **regime**, and a
single fixed input is a regime assumption that was never written down.

### 6.2 A burst probe answering a sustained question

**What happened.** The re-probe (with correct sizes) showed zero errors at every setting. But the
real run holds that load for 60–90 minutes, and under sustained load the endpoint behaved very
differently: at 8 workers the run achieved **126 tokens/second** versus **214** at 1 worker in an
earlier run — the "parallel" setting was more than twice as *slow* as serial, and the service
eventually stopped accepting connections.

**Why it was possible.** Bursts are fast, cheap and easy to script. A sustained test takes an hour.

**What would have caught it.** Stating the question the probe is answering, and checking it matches
the question you need answered. *"Does a burst break it?"* and *"does 90 minutes of load degrade
it?"* are different questions; only the second one mattered here.

> **Throughput.** Work completed per unit time (here, tokens embedded per second). **Latency** =
> time for one operation. Concurrency often improves throughput while making latency *worse* — and if
> the service is shared, the cost lands on other people.

### 6.3 Confirming a null three times: the screen came before the exam, and nobody took the screen

**What happened.** A lever (the depth of a candidate-prefetch stage) was screened on a **40-query
subsample**, which found the mechanism and said the product endpoint probably would not move. A
full 133-query pre-registered A/B was then run: **null**. A second lever (two downstream widths) was
then built into a *second* full pre-registered A/B: **also null**. That is three ~1-hour runs, two of
them spent confirming what the screening pass had already indicated.

**Why it was possible.** Pre-registration — writing down what a run will measure and how its result
may be read, *before* running it — is the house discipline, and it *feels* like rigour. So "build the
next pre-registered A/B" became the default move, and nothing in the process ever asked whether the
question was worth an A/B at all. Pre-registration protects you from interpreting a result after the
fact; it does nothing about choosing a question that cannot produce one.

**What would have caught it.** Two rules, and the first is the one that was missing:

1. **Explore cheap and dirty first.** A screening subsample, an *oracle* instrument (a slow, exact
   reference implementation that is easy to trust), no pre-registration, no negative control. Look for
   signal. Only if the screen says there is something to confirm do you build the powered,
   pre-registered run.
2. **Confirm powered and pre-registered only when the exploration found something.** One confirmation
   per question — not one per configuration of the same question.

> **Resolution floor / minimum detectable effect (MDE).** The smallest difference a study can
> reliably detect, set by the spread of the data and the sample size: roughly `1.96 × SD / √n`. A
> result below it is not "no effect", it is "unmeasurable here" — and re-running the same experiment
> with a new knob does not lower the floor.

**Compute the floor *before* choosing what to test, not after.** On this project's gold set the
sample is fixed at **n = 133** (every labelled query; more means hand-labelling new data), and the
per-query spread on the endpoint is ~0.115. So the floor is `1.96 × 0.115 / √133 ≈ 0.020`. The two
width levers measured **+0.0032 and +0.0025 — about 6× below the floor**, and resolving an effect that
size would need roughly **5,000 queries**. The honest conclusion is not "these levers are bad", it is
**"these levers are out of scope for this ruler"** — and that should have been said before building
either A/B, then recorded so nobody re-tests them.

**Corollary — not every finding is an effect size.** Power analysis is the right lens for a
*ranking-quality* claim ("does this model rank better?"). It is the wrong lens for a *correctness*
finding: a retrieval lane that returns nothing because two halves of the system disagree on a vector
width, a graph traversal whose hop counter is a constant zero, a fusion step that is not
reproducible. Those are bugs. They need a fix, and running them through the statistics lens is what
makes a session feel like it is circling.

### 6.4 A non-deterministic instrument — and a guard defined over the wrong thing

**What happened.** The first full A/B was declared **VOID by its own negative control** (the same
configuration run twice must produce identical numbers). The failure was tiny: on **one** query of
133, the candidate pool held **95 items in one run and 94 in the other**. But it was reproducible, so
it was not a blip. Root cause, found by probing one stage at a time: the vector database's
**server-side rank fusion** — the step that merges several ranked candidate lists into one — returns a
**different fused set on identical inputs**. Measured: one query produced **6 different fused outputs
in 6 runs**; another, 5 in 6. Every individual candidate list was perfectly deterministic, and forcing
exact (non-approximate) search changed nothing.

**Why it was possible.** "Same inputs, same outputs" is assumed everywhere, not checked. And the
control had been defined over *everything the artifact records* — including bookkeeping fields like
pool size — rather than over the **metrics** the study is about.

**What would have caught it.** Three things, all cheap:

1. **Probe determinism stage by stage, and do not assume which stage is guilty.** The first guess here
   was the approximate nearest-neighbour index. It was wrong — the index was exact and deterministic.
   Probing each lane separately located the real culprit in about ten minutes.
2. **Define the negative control on the METRIC, not on diagnostics.** The metrics were **bit-identical
   across both runs** (max difference 0.0); only a bookkeeping count differed. A pool size that wobbles
   while every metric holds still is a **finding about the instrument**, not a reason to void the
   study. Write which one the guard compares, in the pre-registration, before running it.
3. **Measure the noise floor with repeated runs of one configuration before designing any control.**
   Thirty queries × four repeats here gave a spread of **exactly 0.000000** on the endpoint metric —
   which is what licensed reading the run at all.

### 6.5 A number that is not a function of its own artifact

**What happened.** The corrected re-run passed its control. Then the **re-derivability guard** — "can
every summary number be recomputed from the per-query rows the artifact itself stores?" — failed on
**3 values**, by 1e-6. Cause: one metric is returned as a **numpy scalar** rather than a plain Python
float, and a numpy scalar *is* a subclass of `float`, so the JSON writer accepted it silently and the
type was **lost on read**. Re-derivation then used plain floats, and numpy's and Python's rounding
disagree at a decimal tie. Net effect: the artifact's summary was not a function of the file it lived
in.

**Why it was possible.** A subclass passes every type check, so nothing errors; and the difference
only surfaces at a rounding tie, so it looks like noise.

**What would have caught it.** **Coerce scalars to native types at the point of recording** — not at
the point of writing, and never "try the strict path first". The guard is what caught it, which is the
point: the guard was written before it was needed, and it fired on a 1e-6 discrepancy that no human
review would have found.

> **Why this matters beyond one number.** A measurement artifact exists so that someone else can
> recompute your conclusion from the raw rows. If the summary cannot be reproduced from the rows, the
> artifact is a *claim* rather than evidence — and the failure is invisible, because both versions
> print a plausible number.

### 6.6 The record of a failure is worth as much as the record of a success

**What happened.** Three separate things in this stretch were written down *as defects, with the
mechanism measured, and deliberately not fixed in the same session*: the non-reproducible fusion
(6.4), the scalar type leak (6.5), and the fact that a `768`-dimension collection was being queried
with a `1024`-dimension vector. Each got its own register entry, its own reproduction, and a stated
disposition — rather than being silently patched while a measurement was in flight.

**Why it was possible to do well here.** Because the artifacts were on disk: the failing run was
*preserved* under a distinct filename rather than overwritten by the re-run, so the evidence of the
void survived the fix. **A run whose output is overwritten by the next run leaves no evidence it
happened.**

**What to keep.** Name the artifact for the run that produced it, and never let a re-run take the
first run's filename. An unexplained failure that gets overwritten is worse than one that gets
explained.

---

## 7. An opening system prompt for the next project

This is the artefact the project lacked. It is written to be pasted at the start of a new
project/session, and it encodes the specific failures above as rules. It is deliberately blunt.

```
ROLE
You are the engineering partner on a data-science project. The user is a strong data scientist
with limited software-engineering background. Explain jargon inline; never assume they know what
a fixture, a checkpoint, an idempotent operation or a race condition is. Prefer plain claims over
adjectives. When unsure, say so.

THE TWO RULES THAT COME BEFORE EVERYTHING ELSE
1. MEASURE BEFORE OPTIMISING. If we cannot compute a number that tells us whether this change
   helped, we are not ready to make the change. Build the ruler before the thing it measures.
2. DECIDE HOW MUCH WORK WE CAN LOSE. For any job that runs longer than a few minutes, the
   question is not only "how do we stop it failing" but "how much does a failure cost". Answer
   both. A checkpoint beats a retry when the failure is unavoidable.

BEFORE WRITING CODE
- State the success criterion as one sentence with a UNIT, a METRIC, a THRESHOLD and a NEGATIVE
  CASE. Write it down. If you cannot, say so and stop.
- Write the NON-GOALS explicitly. Refuse work against them later.
- For any experiment, compute the required sample size FIRST from the measured noise and the
  smallest effect worth detecting. If the required N is infeasible, say so before collecting.
- Pre-register the decision: what result changes our mind, and what we will conclude if the
  confidence interval spans zero.
- Pin every source of randomness before comparing two configurations. If the harness is not
  reproducible, its numbers are not comparable.

BEFORE ANY LONG RUN
- Print the RESOLVED configuration (after defaults, .env and environment variables) and assert the
  values you intend. Never infer a setting; print it.
- Bound the loss: checkpoint, or write in batches, so a failure costs minutes not hours.
- For every network call: bounded retry with backoff for transient errors, fail fast for
  deterministic ones, and a TOTAL deadline in addition to any per-operation timeout.
- Dry-run on a small fixture against the real dependency first, and record the counts.

WHEN WRITING CODE
- No silent fallbacks. If an except branch changes the meaning of stored data, it must fail loudly
  or mark the degradation where a reader will see it. Never substitute a placeholder value.
- A function's docstring is a test case. If it says "never raises", prove it with a test that makes
  it raise.
- Prefer a required argument over a default that can silently select the wrong input.

WHEN WRITING TESTS
- The test must construct its inputs THE WAY PRODUCTION DOES, not the way that is convenient.
  Reusing objects across two calls can hide an entire class of bug.
- A regression test must be SEEN TO FAIL against the broken version. Do this deliberately: revert
  the fix, watch the test fail, restore the fix. State in the commit that you did it.
- Assert the property that is actually guaranteed, not one that merely looks strict. A test that
  fails randomly trains people to re-run instead of investigate.
- For a measurement, test against an oracle that did not produce the data under test.

VERIFICATION AND REVIEW
- An independent reviewer (human or model) is a FILTER, not a PROOF. Treat a fast clean pass as no
  signal. Verify each specific claim it makes against the running code, and record which claims
  were false.
- Before trusting a result, verify the HARNESS. A defect in the measurement code is
  indistinguishable from a finding about the system.
- A plan's verification step must be a PROPERTY check, not a count check. Ask: what would this look
  like if the thing were broken?

DOCUMENTATION
- Register every finding in the repo's living documents as its own entry with: what happened, why
  it matters, the evidence, the cost to fix, and whether it blocks anything. A finding mentioned
  only in chat is a finding lost.
- Keep a current-state file that loads every session, a durable architecture file, and a backlog.
  Separate "what is true now" from "what we intend to do".

HOW TO TALK TO ME
- Lead with the result, then the evidence. No preamble, no restating my request.
- Flag assumptions and ambiguities explicitly rather than resolving them silently.
- Give me the WHY behind a decision and why the alternatives were rejected.
- If you cannot do something, say so plainly and offer the alternative. Never fabricate a result.
- Tell me when to start a fresh session, and give me a handoff note when you do.
```

---

## 8. Checklist — the one-page version

**Before starting**
- [ ] Success criterion written as one sentence: unit + metric + threshold + negative case
- [ ] Non-goals written down
- [ ] The measuring instrument (labelled evaluation set) built from a source the system cannot see
- [ ] Sample size computed from measured noise, before collecting
- [ ] Minimum detectable effect computed from that noise — any lever whose plausible effect sits below
      it is recorded as out of scope, **not tested** (§6.3)
- [ ] Decision pre-registered: what result changes our mind
- [ ] Sources of randomness pinned; harness reproducibility measured
- [ ] The pre-registration says whether the negative control compares **metrics** or everything
      recorded (§6.4)

**Before every long run**
- [ ] Resolved configuration printed and asserted
- [ ] Checkpoint / batch-write in place, so the loss window is bounded
- [ ] Retry with backoff + a total deadline on every network call
- [ ] Dry run on a small fixture against the real dependency
- [ ] Verification defined as a property check, not a count check

**While writing code**
- [ ] No silent fallbacks that change the meaning of stored data
- [ ] Docstring promises backed by tests that would catch their violation

**Before believing a result**
- [ ] The harness itself has been verified
- [ ] Every summary number re-derives from the artifact's own per-item rows (§6.5)
- [ ] Tests exercise the production shape, and regression tests have been seen to fail
- [ ] Independent review treated as a filter; its claims adjudicated against the code
- [ ] Findings registered in the living documents, each as its own entry
- [ ] A failed run's artifact preserved under its own name, never overwritten by the re-run (§6.6)

---

## 9. What worked — keep doing these

The failures above are worth reading next to the things that repeatedly saved this project.

- **An independent oracle.** Verifying page numbers against a *different* PDF text extractor, and
  grading pages with a vision model reading the page image, are the two checks that held up under
  scrutiny. Both work because the oracle never sees the data it is judging.
- **Reframing instead of forcing.** When the "two page-numbering systems" problem turned out to be
  one system with inherent ±1 fuzz, the response was to re-derive it, prove it, and re-register the
  item as a known noise floor — not to keep chasing a defect that did not exist.
- **Recording what was *not* proven.** Marking a result "unresolved at n=133" and a verification
  "fail-closed with no real defect" rather than smoothing them into a pass is what makes the rest of
  the record trustworthy.
- **Refusing to bundle.** When a tempting change appeared mid-fix (parallelising two more lanes),
  it was registered with its arithmetic and deliberately left out, because it needed its own
  measurement first. This is the discipline that keeps a change reviewable.
- **Measuring the cost of a probe's blind spot.** §6.1 was found by re-reading a *previous* probe
  and asking what regime it had actually tested. That habit is worth institutionalising.
- **Guards written before they were needed.** The re-derivability check (§6.5) and the negative control
  (§6.4) both fired on discrepancies far too small for a human review to notice — 1e-6 on one number,
  and one item of 133. A guard is worth its cost precisely when it fails on something you would
  otherwise have waved through.
- **Overturning a hypothesis by elimination, cheaply.** The first explanation for the non-reproducible
  run was the approximate search index. Probing each stage separately — four short scripts, minutes
  each — replaced it with the right one and *proved* the first was innocent, instead of arguing about
  it. When two stages could both be guilty, measure them one at a time rather than reasoning.
- **Preserving the evidence of a failure.** The void run's artifact was copied aside under a distinct
  name before the corrected re-run took the canonical filename, so the thing that documented the
  failure stayed checkable afterwards. Failures that get overwritten cannot be learned from.
- **Registering a defect instead of quietly fixing it.** Three findings in this stretch were written up
  with their mechanism measured and deliberately left unfixed, because a measurement was in flight and
  a silent patch would have changed the instrument mid-experiment.
