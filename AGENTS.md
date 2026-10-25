# Permanent Agent Instructions & Operating Protocol

> **System:** Bihar Cyber Hackathon 2026 PS-05 — Digital Evidence Authenticity & Integrity Verification Platform  
> **Target Audience:** Any AI coding agent, subagent, or newly authenticated AI account resuming work on this repository.  
> **Rule of Action:** Adhere strictly to the operational protocol below. Do not deviate or invent non-standard conventions.

---

## 1. Core Operating Commandments

Every AI agent working on this codebase must follow these twelve rules unconditionally:

1. **Read `HANDOFF.md` and `PROJECT_CONTEXT.md` before starting.** These are your primary briefing documents.
2. **Read `CURRENT_TASK.md` if a task is marked in progress.** If no active task is running, do not fabricate one.
3. **Inspect Git status and the active implementation before changing code.** Check `git status` and test status before writing any new code.
4. **Read only documentation and source files relevant to the current task.** Never load the entire repository into context.
5. **Do not reread the entire work log, decision history, or roadmap by default.** Consult `AI_WORKLOG.md` or `DECISIONS.md` only when specifically seeking prior historical context on a component.
6. **Do not repeat completed work unnecessarily.** Prompts 1 through 8 (Phases 1–8) are verified. Do not rebuild working modules.
7. **Make minimal, focused changes and preserve existing architecture.** Maintain layer separation: routes -> domain services -> repositories -> storage adapters.
8. **Run relevant tests and record actual outcomes.** Always execute the appropriate test suite (pytest, typecheck, lint) and report actual exit codes and counts.
9. **Update documentation after every meaningful implementation milestone.** Keep `CURRENT_TASK.md`, `AI_WORKLOG.md`, `TASK_TRACKER.md`, and `HANDOFF.md` aligned with reality.
10. **Never fabricate prompts, code changes, decisions, or test results.** If an output or previous prompt is unknown, explicitly label it as an estimated summary.
11. **Never store credentials, API keys, or secrets in documentation or commits.** Use `.env` with strict exclusions via `.gitignore`.
12. **Never mark unverified work as verified.** A task is only "Verified" when automated tests have passed cleanly and code passes static analysis.

---

## 2. Session Startup Protocol (Token-Efficient Entry)

To maximize your token budget and prevent context bloat:

```text
[Start of Session]
  │
  ├── 1. Read AGENTS.md (Operating constraints)
  ├── 2. Read HANDOFF.md (Current system baseline, test counts, entry points)
  ├── 3. Read CURRENT_TASK.md (Check if an interrupted task exists)
  ├── 4. Consult PROJECT_CONTEXT.md (Only sections relevant to the task)
  ├── 5. Run `git status` (Inspect working tree state)
  └── 6. Proceed to inspect only target task files
```

- **Do NOT** read `docs/PLAN.md`, `docs/ARCHITECTURE.md`, `docs/DATA_FLOW.md`, or `DECISIONS.md` in full unless your task specifically involves modifying those architectural boundaries.
- **Do NOT** cat or print entire large files. Use line-slice viewing (`view_file` with `StartLine`/`EndLine`) or targeted ripgrep (`grep_search`).

---

## 3. Implementation Workflow

During task execution:
1. **Targeted Inspection:** Inspect only the specific route, service, repository, or UI component under modification.
2. **Atomic Modification:** Keep changes surgical. Respect existing conventions (Async SQLAlchemy 2.0, Pydantic v2 schemas, Next.js 14 App Router).
3. **Run Verification:**
   - Backend tests: `..\..\.venv\Scripts\python -m pytest <target_test_file> -v`
   - Backend types: `..\..\.venv\Scripts\mypy --config-file mypy.ini app tests`
   - Frontend types: `npm run typecheck` (in `apps/web`)
   - Frontend lint: `npm run lint` (in `apps/web`)
4. **Milestone Documentation:**
   - While work is underway: Keep `CURRENT_TASK.md` updated with completed sub-steps.
   - Upon completing a milestone: Append an entry to `AI_WORKLOG.md`, update `TASK_TRACKER.md`, and refresh `HANDOFF.md`.

---

## 4. Safe Account-Switching & Usage Limit Protocol

When approaching AI token limits or switching AI accounts:

1. **Cease New Changes:** Stop creating new code edits immediately.
2. **Preserve Editor State:** Save all active files to disk.
3. **Record Exact State in `CURRENT_TASK.md`:**
   - Current prompt/objective.
   - Files modified in the session.
   - Last confirmed successful step.
   - Exact error or last executed command.
   - Concrete next steps in sequential order.
4. **Update `HANDOFF.md`:** Record latest verified test status, blocker summary, and immediate next action.
5. **Append `AI_WORKLOG.md`:** Log the session work, tests executed, and exit codes.
6. **Handoff Verification:** The incoming agent must read `HANDOFF.md`, check `CURRENT_TASK.md`, run `git status`, and run the test suite to confirm the baseline before touching code.

---

## 5. Non-Negotiable Forensic Domain Invariants

The PS-05 platform operates under strict forensic integrity and chain-of-custody standards (ISO/IEC 27037, NIST SP 800-86, FRE 901/902):

- **Bitstream Preservation:** Original evidence bytes must never be modified in-place under any circumstances.
- **Read-Only Vault Locking:** All ingested originals in `storage/originals/` must be locked read-only (`chmod 0400` / `stat.S_IREAD`).
- **Separate Artifact Storage:** Derivative outputs (ELA heatmaps, spectrograms, video frames, PDF reports) must reside strictly in `storage/artifacts/` or `storage/reports/`, never in `storage/originals/`.
- **Primary Hash Immutability:** `evidence_items.primary_hash_sha256` is permanently locked upon creation. Database triggers abort any SQL `UPDATE` to this field.
- **Append-Only Audit Log:** The `audit_events` table is physically append-only. Triggers prevent any SQL `UPDATE` or `DELETE` with `CRITICAL SECURITY VIOLATION`.
- **Scientific Integrity of Findings:** ELA, STFT spectrogram anomalies, and metadata gaps are investigative indicators, never definitive legal proofs of tampering. Reports and APIs must distinguish between objective physical observations, technical interpretations, and forensic limitations.
