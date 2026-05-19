# SWC-Studio Provenance & Versioning — Reading Script

Companion to `docs/SWC-Studio_Provenance.pptx`. Read each section as
you advance the matching slide. Designed for a 12–15 minute walk-
through; trim italicised paragraphs for a tighter 7–8 minute version.

---

## Slide 1 — Title

> *"Today I'm walking through the new provenance and versioning
> system for SWC-Studio. It's a git-shaped layer that records every
> change made to every neuron file, with full revert, full AI
> reproducibility, and a small on-disk footprint. I'll cover why we
> needed it, how it's structured, what's been built, and what we'll
> wire up next."*

---

## Slide 2 — The old logging had four hard limits

> *"Before this work, every edit to an SWC produced a timestamped
> output file and a sidecar text report. That covered the basic 'what
> just happened' question, but not much more."*

Walk the four bullets in order:

- **No trace of who.** The reports recorded the operation, but not the
  actor, the tool version, the git SHA, or the runtime environment.
- **No way to revert.** Older versions of the file piled up next to
  the source, but there was no concept of "go back to last Tuesday."
- **No AI reproducibility.** Auto-typing runs didn't capture the
  model SHA, RNG seed, or Python environment. If a colleague wanted
  to recompute the same labels next year, they couldn't.
- **Output folders ballooned.** Each operation wrote a full SWC copy
  plus a text report. After 100 edits you had hundreds of redundant
  files.

> *"All four are solvable individually, but the cleanest fix is one
> coherent system that handles them together."*

---

## Slide 3 — Five non-negotiable goals

> *"Before designing anything, we locked in five goals. Each one was
> a hard requirement, not a nice-to-have."*

- **Provenance** — who, what, when, with which tool.
- **Revertable** — go back, and branch from a past state to redo
  without losing the original path.
- **AI reproducible** — capture enough to recompute the same result.
- **Compact** — delta-encoded, deduplicated, compressed.
- **Clean** — human-readable log, SQL-queryable, self-describing files.

> *"These five drove every architectural decision on the next slide."*

---

## Slide 4 — Borrow, don't invent

> *"The most important design principle: nothing in this system is
> invented. Every individual mechanism is a battle-tested pattern
> from another community. We just blended them for SWC."*

Walk the table briefly. Key callouts:

- "Content-addressed blobs and the refs layout are literally git's
  internal data model, with `heads/` renamed to `branches/`."
- "The append-only event log + SQLite as a read-model is the standard
  event-sourcing + CQRS pattern from the database community."
- "The two-line `@PROV` header in the SWC itself is borrowed from
  the `@PG` chain in SAM/BAM, which genomics has used for 15 years."
- "The AI run schema mirrors MLflow field-for-field, even though we
  don't have MLflow as a runtime dependency — so future integration
  is a 30-line adapter."

> *"Net: if a contributor knows git, they recognize 80 percent of the
> layout on sight. We have nearly zero novel risk."*

---

## Slide 5 — Per-file `.history/` inside the output folder

> *"Now the actual layout on disk. For each SWC file, there's a
> sidecar output folder — same as today. The new piece is the
> `.history/` subdirectory inside it."*

Walk the tree top to bottom:

- The original SWC is **never touched**. Read-only forever.
- `<stem>_current.swc` holds the latest state. It gets overwritten on
  every commit. This is the file the user actually opens and edits.
- Optional checkpoints — files like `<stem>_pre_paper.swc` — are
  user-marked snapshots of specific past commits. Only created when
  the user asks.
- Inside `.history/`:
  - `version` — a single integer, the format version. Currently `1`.
  - **`events.jsonl`** — one growing text file, the timeline.
    Every commit is one line.
  - **`objects/`** — many small compressed blobs, sharded into
    2-char prefix subdirectories like git does.
  - **`refs/`** — bookmarks: `HEAD`, branches, tags. Each is a tiny
    text file.
  - **`index.sqlite`** — the query cache, rebuildable from
    `events.jsonl` at any time.
  - **`lock`** — only present while a write is in progress; an OS
    advisory lock prevents two processes from clobbering each other.

> *"Move the SWC and this output folder together, and provenance
> survives — the dataset is self-contained."*

---

## Slide 6 — Three layers, one source of truth

> *"It helps to think of this as three layers that each do one job."*

Walk the three cards left to right:

- **`events.jsonl` is the source of truth.** One JSON object per
  line, append-only, fsynced on every write. You can `cat` it,
  `grep` it, `tail -f` it. Each line is chained to the previous
  commit by parent SHA — that's the DAG.

- **`objects/` is the heavy detail.** Each blob is named by the
  SHA-256 of its uncompressed content. That means deduplication is
  automatic — two operations that produce the same diff share one
  blob. Same for environment captures: a hundred AI runs in the same
  Python env store one env blob.

- **`index.sqlite` is the query cache.** It exists purely to make
  "who did what when" fast. If it ever gets corrupted, you run
  `swcstudio history reindex` and it rebuilds from `events.jsonl` in
  seconds.

> *"Important: SQLite is never the source of truth. JSONL always wins
> if they disagree."*

---

## Slide 7 — Four kinds of blob, all SHA-named

> *"Inside `objects/` there are four kinds of blob. Different
> operations produce different numbers of them."*

Walk the table:

- **Diff** — the actual list of node-level changes plus topology
  changes. Created for every mutating op.
- **Snapshot** — a full canonicalized SWC, taken every 50 operations.
  Used as anchor points so revert doesn't have to replay 500 diffs.
- **AI run** — MLflow-shaped record: model SHA, params, metrics,
  env hash, artifacts. Only created for AI ops.
- **Env fingerprint** — full OS + Python + every installed package.
  Created only for AI ops, **deduplicated**, so a hundred AI runs in
  the same env share one blob.

> *"The bottom line is the magic: filename equals SHA of content.
> That gives us tamper detection, automatic dedup, and immutability
> for free."*

---

## Slide 8 — The keystone API

> *"Here's the one entry point everything routes through. CLI
> handlers, GUI actions, and plugins all use this same context
> manager. Nothing else is allowed to mutate an SWC — that's how we
> guarantee provenance is never bypassed."*

Walk the code:

- User enters the `with` block, gets `op.input_bytes` (the latest
  committed state).
- Mutates them however they like.
- Calls `op.set_output(new_bytes)`.

> *"On exit, the wrapper handles everything in the comment block:
> acquires the lock, snapshots input, captures env for AI ops,
> computes the structured diff, writes blobs, appends the event,
> advances the branch ref atomically, updates the SQLite index, and
> rewrites `current.swc` with a refreshed `@PROV` header. Then it
> releases the lock. If anything fails, the lock is released and no
> partial state is left behind."*

---

## Slide 9 — Bounded 2-line `@PROV` header

> *"Even with the sidecar, we wanted the SWC file itself to be
> self-describing. So we borrowed the SAM/BAM `@PG` chain idea — but
> bounded it to exactly two lines, never more."*

Walk the code block:

- **Line 1 (root)** — written once, never changes. Tells you the
  original file identity and when it was created.
- **Line 2 (tip)** — overwritten on every commit. Current state, the
  parent it descends from, total commits, the tool that produced it,
  the actor, the timestamp, and where the full sidecar lives.

> *"Always two lines, no matter if there are 20 commits or 2000. The
> full chain stays in the sidecar; the file just carries a business
> card pointing to it. And these two lines are excluded from the
> canonical hash, so updating the tip line never changes the file's
> own identity. That's the cycle-free property — the header can talk
> about its own state without recursively invalidating itself."*

---

## Slide 10 — Branching DAG

> *"Branching is the same model as git, just per-SWC. Branches let
> you 'redo from a past snapshot' without losing the original path."*

Walk the small commit graph:

- `main` is the active branch by default.
- Branch off any past commit to try an alternative — both paths now
  coexist.
- Tag any commit with a permanent name like `submitted_to_paper`.

> *"Revert in this system is read-only — `checkout` materializes any
> past state into a file, but doesn't change history. To actively
> work from a past state, you create a branch from that sha. The
> original branch stays exactly where it was."*

---

## Slide 11 — AI reproducibility

> *"AI runs are the highest-stakes case for provenance, so they get
> the most metadata."*

Left side, what's captured:

- The model itself by SHA, plus the human-readable version label.
- Every parameter the AI was called with, including the RNG seed.
- The full command line.
- Input and output file SHAs.
- The tool that ran it, with git SHA when available.
- The whole runtime environment — operating system, Python version,
  CPU/GPU, CUDA version.
- Every installed Python package and its version, via
  `importlib.metadata`.

Right side, the reproduce.yaml:

> *"A colleague who wants to recompute the result runs
> `swcstudio history reproduce <sha>` and gets a small YAML file
> that captures everything. They `swcstudio reproduce
> reproduce.yaml` on their machine; if their env matches it just
> runs, if not it warns them about the deltas."*

> *"And because env captures are deduplicated, you can do this
> hundreds of times in the same environment without any storage
> cost beyond the first capture."*

---

## Slide 12 — `swcstudio history` — 12 verbs

> *"On the terminal side, there's a new tool group with twelve
> verbs. All twelve ship in v1 — they're all built and tested."*

Briefly call out the high-leverage ones:

- `log` — your timeline, filterable by actor, date range, branch.
- `show <sha>` — full detail of one commit, with the diff and AI
  metadata.
- `checkout <sha>` — materialize any past state as a read-only
  file.
- `branch <name> --from <sha>` — fork a past state to redo.
- `tag` — permanent milestones.
- `reproduce` — the AI YAML we just saw.
- `gc` — clean up unreferenced blobs (manual only — never automatic).
- `export-crate` — bundle everything as an RO-Crate for publication.

Show the bottom example as the "everyday" command shape.

---

## Slide 13 — GUI: new "History" top-level menu

> *"On the desktop side, there's now a top-level History menu in the
> main window, between Window and Help."*

Walk the two items:

- **Open History Browser…** — opens a full timeline panel for the
  currently loaded SWC. Sortable commit table, filter chips, right-
  pane detail view, and buttons for switching branches, branching
  off, tagging, and marking checkpoints.

- **Initialize History for This File…** — for SWCs that already
  have an old `_swc_studio_output/` folder from before this work.
  It creates a synthetic "import" commit anchored at the most
  recent `_closed_*.swc`, and from that point forward every
  mutation is tracked. Safe to run twice — it's idempotent.

> *"That's the entire GUI integration so far. The History browser is
> a self-contained panel; adding more advanced views like a visual
> DAG renderer is on the future-work list, not v1."*

---

## Slide 14 — Where we are

> *"Final slide — current state."*

**Left card — what's done:**

- The complete design spec, 20 sections.
- Eight core modules in `swcstudio.core.provenance` covering
  everything from the canonical hash to the keystone context manager.
- All twelve CLI verbs.
- RO-Crate export.
- The GUI History panel + main_window menu wiring.
- A reference handler conversion + the conversion guide.
- The `zstandard` dependency declared, the plugin contract updated.
- About 6,400 lines of code, all in the new package; 29 invariants
  pass end-to-end.

**Right card — what's left:**

- Fifteen single-file CLI handlers, five batch handlers, thirteen
  GUI main_window slots, five panel-side mutation methods — each
  one needs a small, focused conversion to `tracked_op`.
- One final commit to delete the old `swcstudio.core.reporting`
  module after every caller has been moved.
- Total: 38 small commits, tracked in the rewire checklist doc.

> *"The agreed working pattern is item by item: I write the
> conversion as a diff, you run the corresponding command or click
> through the GUI to confirm behavior, we commit, and move on. None
> of it is destructive — every step lives on the
> `data-version-control` branch, and `main` is bit-identical to where
> we started."*

> *"Questions?"*

---

## Appendix — useful commands during the walkthrough

If you want to live-demo any of this during the talk:

```bash
# Show this branch sits on top of main
git checkout data-version-control
git log --oneline ^main

# Run an op end-to-end on a sample file
python -m swcstudio.cli.tracked_handlers_example \
    --file demo.swc --node-id 2 --new-type 4

# Now query the history
swcstudio history log demo.swc
swcstudio history show <short_sha>
swcstudio history verify demo.swc
swcstudio history export-crate demo.swc -o demo_crate

# And open the GUI to see the History menu
swcstudio-gui
```
