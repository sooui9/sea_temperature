# sea_temperature (우리 바다 안심도우미)

Team project: a proactive high-sea-temperature consultation dashboard for staff who contact aquaculture farms (contact list, farm detail, sea-temperature forecast, consultation status). Four developers share one repo through forks and PRs, so **team ownership rules come first** (see below).

Rule files for VS Code live in `.github/instructions/` (GitHub Copilot attaches them by `applyTo`/`description`). Other agents (Claude Code, Codex) must open the file named in each "Details" line when the task matches.

## Run and test (only what code does not show)
- HTML screens: with the backend running, visit `http://127.0.0.1:8000/` (same as the Render deploy), or run `py -m http.server 8765` at the repo root and visit `http://localhost:8765/consult_home.html`. Opening a file directly (`file://`) shows sample data only. No build step, no framework.
- Backend: from `backend/`, `..\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000` (needs `backend/backend/.env` copied from `team.env.example`).
- Tests: `py backend/run_tests.py` (no DB), `py backend/run_tests.py --db` (temporary schema, rolled back), `node --test "tests/**/*.cjs"`.

## Team ownership (non-negotiable)
Other teammates' code is read-only for you unless the user explicitly approves a specific change.
- Before editing any existing file, check its owner in `docs/OWNERSHIP.md`. If it is not listed, run `git log --format=%an -- <file>` and, for co-authored files, `git blame -L <range> <file>` on the lines you would touch. Compare with `git config user.name`.
- Owner is someone else, or unknown: do not modify, delete, rename, move, or reformat it. Show the proposed diff, the reason, and the owner's name, then wait for the user's explicit approval of that file.
- Never delete or "clean up" teammates' code, tests, comments, or docs, even if it looks unused or wrong. Report it instead.
- Never discard others' work through git (`reset --hard`, `checkout --`, `restore`, `clean`, `stash drop`, force push, or picking one side in a merge conflict).
- Prefer adding new code in a new file or in your own section over changing shared code.
- Details: `.github/instructions/team-ownership.instructions.md`.

## Communication and language
- Reply to the user in Korean. Lead with the result. No preamble, no recap of the request, no closing summary of what the diff already shows.
- Follow the repo's existing language: README and docs in Korean, UI text in Korean, commit messages in Korean (see Git section). Code comments match the file you are in (frontend files use Korean, Python uses English). Identifiers stay in English.

## Anti-slop (code quality)
- Do exactly what was asked. No unrequested features, refactors, files, or docs (no stray README/*.md).
- Read existing code first and match its patterns, naming, and libraries. Reuse before writing new helpers.
- Do not add a dependency for something the stdlib or an existing dependency does.
- No speculative abstraction: no wrapper, interface, config option, or factory with a single use.
- No dead code, commented-out code, unused imports, or placeholder TODOs in code you write. Dead code in teammates' files is reported, not removed (team ownership wins).
- Comments explain why, never what. Do not narrate the code.
- No blanket try/catch, no swallowed errors, no invented fallbacks. Handle only errors that can occur; surface the rest.
- Do not invent APIs, flags, table names, or package names. If unsure, check the source or docs, or say so.
- Never claim "done" or "fixed" without running the relevant test. If it cannot be run (for example no DB access), say so.
- Keep diffs minimal and scoped. Do not reformat or rename unrelated code.
- When a change adds or changes a screen, API, or run step, update the matching row in `README.md` only if the user asked for docs or the change would leave README wrong. Ask if unsure.

## Token economy
- Search before reading: grep or glob first, then read only the needed line ranges. Do not read whole large files (`farm_detail.html`, `consult_home.html`, `backend/backend/farm_detail.py`) or re-read unchanged ones.
- Never read or print lockfiles, `__pycache__`, `.venv`, logs, images, or `.local/` unless the task is about them.
- Pipe noisy commands to a file or filter them; never dump full command output into context.
- Batch independent tool calls in parallel.
- Prefer a targeted edit over rewriting a file.
- Ask one concise question only when a wrong guess would be costly; otherwise choose a sensible default and state it.
- Do not add content that changes weekly to this file or to `.github/instructions/`.
- If `graphify-out/graph.json` exists, follow `.github/instructions/graphify.instructions.md` before exploring.

## Security (non-negotiable)
- Never hardcode or log secrets, tokens, keys, passwords, or personal data (names, birth dates, phone numbers). Read secrets from environment variables.
- Never read, print, or commit `.env*` (except `*.env.example`), key files, or credentials. Each teammate's DB account and password stay in their own `backend/backend/.env`.
- The browser never connects to the DB. All data goes through the FastAPI backend.
- Validate and sanitize all external input; use parameterized queries; encode output.
- No destructive commands (`rm -rf`, `git reset --hard`, force push, `DROP`/`TRUNCATE`/`DELETE`/`ALTER` on the shared DB) without explicit user approval. Schema changes and `init-db` belong to the DB server admin.
- Add dependencies only from well-known sources, with pinned versions. Flag anything suspicious.
- Details: `.github/instructions/security.instructions.md`, `.github/instructions/backend-db.instructions.md`.

## Git and GitHub
- Commit only when asked. Never push, force-push, or rewrite history without explicit approval.
- Work on a branch per screen or feature in your own fork and send a PR to the team repo. Do not commit straight to a teammate's branch.
- Before any commit: no secrets or personal data staged, only your own files staged (or approved changes), `.gitignore` covers generated and local files.
- Details: `.github/instructions/github-release.instructions.md`.

## Frontend and design
- HTML screen conventions (side menu, localStorage, `API_BASE`, wording): `.github/instructions/frontend.instructions.md`.
- For UI/UX design or review work, read `DESIGN.md` first. Values marked `UNDECIDED` are unapproved; never choose them without user approval. Details: `.github/instructions/ui-design.instructions.md`.
