# oneShotTranscoder

Transcodes MKV files for Apple TV.

Canonical instructions and memory contract for AI agents working in this repository. `CLAUDE.md` and `GEMINI.md` point here.

## Start of session

1. Read `ai/memory/PROJECT.md` for identity, purpose, stack, and constraints.
2. Read `ai/memory/CURRENT.md` for immediate state and active priorities.
3. Consult `project.yaml` for workspace metadata.
4. Read `README.md` for architecture, runtime details, and usage.

## Agent orchestration and delegation

- The primary conversation agent acts as the coordinating and planning agent.
- Delegate bounded, parallelizable tasks—such as codebase research, multi-file inspections, checks, and isolated implementation—to fast, cost-effective subagents wherever supported by the harness.
- Maintain single-writer discipline: assign non-overlapping files or scopes to concurrent subagents, and never allow multiple agents to edit `ai/memory/CURRENT.md` or the same file simultaneously.
- Keep architectural decisions, cross-cutting synthesis, and final verification in the coordinating agent.

## End of session

1. Verify changes with tests or build checks where applicable.
2. Update `ai/memory/CURRENT.md` with new state, completed work, and next priorities.
3. Review `git status` and diffs to ensure clean, focused commits.
