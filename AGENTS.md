You are AI coding assistant working in a collaborative benchmark repository. Default to proposal-first behavior: you propose changes and wait for approval before applying edits.

Work is review-driven via GitHub PRs.

Instruction layering (repo-wide vs local)
This file (AGENTS.md) defines repository-wide, shared team policy and should remain user-agnostic.

Optional personal preferences may be defined in AGENTS.local.md (ignored by git by default): - AGENTS.local.md can refine communication style and personal workflow preferences. - AGENTS.local.md must not weaken safety, validation, reproducibility, or PR workflow rules from this file. - If guidance conflicts, follow this file (AGENTS.md) for repo decisions.

Operating mode: proposal-first (default)
Before making any code edits, do the following: 1) Summarize your understanding of the request in 2–5 bullets. 2) Propose a step-by-step plan. 3) List the exact files you intend to change/create. 4) Wait for explicit approval to apply edits (e.g., "go ahead", "apply", "make the changes").

After edits are applied: - Run relevant checks (see Validation). - Report results and provide a PR-ready summary.

Exceptions: - You may create temporary notes in chat (not files) without asking. - You may run safe local commands (below) without asking.

Collaboration and visibility expectations
Assume collaborators want visibility into ongoing work.
While working, provide brief progress updates at meaningful milestones:
what you inspected
what you plan to change next
what changed after edits/checks
Surface assumptions explicitly.
If tradeoffs are non-obvious, pause and ask before committing to one path.
Do not make silent, broad, or surprising changes.
Safe local commands (allowed without asking)
You may run commands that only read information or perform lightweight validation, such as: - Listing files / searching code: - ls, dir, find, rg, git status, git diff, git grep - Reading environment info: - python --version, python -c "...", pip show ... - Running fast checks: - python ci/run_cpu_checks.py - pytest -q (or targeted tests) - Viewing repo docs/configs: - cat, type, opening markdown/yaml/json files

Do not run long benchmarks, large downloads, or network-heavy commands without asking.

Actions that require explicit approval (always ask)
Ask first before: - Adding/removing dependencies or changing requirements files (requirements*.txt, lockfiles) - Changing CI/workflows/hooks (.github/workflows/**, ci/**, .githooks/**, scripts/setup_git_hooks.py) - Changing database schema or result formats (results/**, SQLite schema, export scripts) - Refactoring/reorganizing directories, renames, or mass formatting - Changing benchmark methodology/metrics in a way that affects comparability - Downloading models/datasets, or any large network activity - Touching secrets/credentials or introducing telemetry/tracking

Repo intent and architecture (preserve)
This repository is a multi-modal benchmark framework: - runners/: category benchmark runners (stt/tts/vlm/etc.) - utils/: shared utilities (config, resolver, DB, GPU, cache, manifests, preflight) - app/: Gradio UI built on top of runners/utils - config/models/: YAML model configs per category - tests/: tests for runners and utilities - scripts/: data prep, exports, helper scripts - results/: benchmark DB and artifacts

Keep these boundaries. Prefer adding shared logic to utils/ rather than duplicating across runners.

Change policy: keep PRs small and focused
Minimal diff that solves the requested task.
No "cleanup crusades" (no unrelated style changes, no sweeping refactors).
If you notice unrelated issues, mention them as a short "Optional follow-ups" list.
Code quality and maintainability standards
Keep code easily explainable for current and future team members.
Prefer simple, explicit implementations over clever abstractions.
Add concise comments/docstrings where behavior is non-obvious.
Avoid unnecessary complexity while preserving efficiency and professional quality.
Tooling baseline
When modifying code or technical docs, keep repository tooling and standards in mind: - Format: black - Lint: ruff - Types: mypy (currently scoped) - Validation direction: likely pydantic adoption for stronger schema/contract validation

Guidance: - Avoid introducing style/type regressions. - Prefer maintaining or improving type hints in touched code. - For config/contracts/validation paths, favor structures that can migrate cleanly to Pydantic.

Hugging Face / model handling policy
Do not silently download models on import.
Prefer explicit user action or clear runtime messaging if a download is required.
Record or expose model identifiers/settings where appropriate (model id, revision, dtype/device, backend).
Benchmark correctness & reproducibility
When modifying benchmarks or metrics: - Preserve existing metric definitions unless explicitly asked to change them. - If a metric changes, document: - what changed - why - how it impacts comparability with older runs - Prefer backward-compatible additions.

Validation (default expectations)
For any non-trivial change, run: - python ci/run_cpu_checks.py

Additionally: - If changes touch runners/ or utils/, run targeted pytest modules relevant to the change. - If changes touch runtime paths (app/, runners/, utils/, config/models/, scripts/, ci/), remind the user about GPU smoke workflow expectations (Windows 2080 Ti manual dispatch, Linux GPU workflow on 3090/5090 where applicable).

If you cannot run a check, explain why and provide exact commands for the user to run.

GitHub / PR workflow and repository state discipline
This repository is PR-driven. All changes flow through review.

Core rules
Do not commit, push, merge, rebase, reset, or pull unless explicitly instructed.
Assume "no direct push to main".
All changes go through PR.
When proposing changes, provide a PR-ready summary including:
What changed
Why
How to test
Risks / limitations
Never modify branch history or remote state without explicit user instruction.

Repository status protocol (local vs remote clarity)
When the user asks about repository status, branch sync, or whether "everything is synced / working correctly", you must perform a full local + remote comparison, not just git status.

Required steps:

Fetch remote state (read-only):
git fetch --all --prune

Report separately and explicitly:

A) Local working directory - Output of git status - Uncommitted changes - Untracked files

B) Current local branch - Branch name - Whether it tracks a remote branch - Ahead/behind count relative to upstream

C) Remote tracking branch (if exists) - Compare HEAD to @{u} - Show commits ahead/behind

D) Local main vs origin/main - Compare both directions - Clearly state: - "Local main is ahead by X commits" - "Local main is behind by Y commits"

Clearly label every section as:
LOCAL (working tree)
LOCAL BRANCH
REMOTE TRACKING
REMOTE MAIN

Never assume local state represents remote state.

Do not perform merge, pull, rebase, or reset unless explicitly requested.

If CI status is relevant (e.g., on a PR branch), mention whether the latest commit locally matches the latest commit on the remote tracking branch before discussing CI.

Documentation guidance hierarchy
Root AGENTS.md defines repo-wide rules.
Nested AGENTS.md files provide folder-specific guidance.
Use the most local applicable guidance first, then parent guidance.
Personal preferences belong in AGENTS.local.md, not in shared repo policy files.
When to stop and ask clarifying questions
Stop and ask if: - The request is ambiguous (which runner/model/config is canonical) - The change would affect benchmark comparability - There are multiple plausible places to implement (runner vs utils vs app) - The change may trigger large downloads or long runtime