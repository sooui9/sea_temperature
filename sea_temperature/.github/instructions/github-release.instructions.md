---
name: Git and GitHub
description: Use when committing, branching, merging, pushing, creating a PR, syncing a fork, or preparing the project for a public GitHub release.
---

# Git and GitHub rules

## Team workflow
- The team repo is `sooui9/sea_temperature`. Each member works in their own fork.
- Sync the fork with the team repo before starting work. One branch per screen or feature (`loading-screen`, `insurance-data` style names).
- Open a PR to the team repo. The owner of any teammate file you changed reviews it (see `docs/OWNERSHIP.md`).
- Never commit to, push to, or rebase a teammate's branch.

## Pre-commit gate
1. `git status` and review the staged diff. Stage files by name, never `git add -A` or `git add .`.
2. Every staged file is the current user's, or the user approved the change (team ownership rules).
3. Scan staged changes for secrets and personal data (keys, passwords, `.env`, names, phone numbers, real farm records).
4. Confirm `.gitignore` covers `.env`, `.venv/`, `__pycache__/`, logs, and local data. Files already tracked by mistake (for example `__pycache__/*.pyc`) need `git rm --cached`, and only with approval, because it is a shared change.
5. Run the tests that cover the change (see `AGENTS.md`). If they cannot run, say so.

## Commits
- Follow the existing history: a short Korean summary, `화면/기능: 무엇을 바꿨는지` when it helps.
  - Good: `보험 정보: 세부 내용 창을 화면 가운데 팝업으로 변경`, `로딩 화면 추가 (loading.html, ?state= 로 4가지 화면)`
  - Bad: `수정`, `pycache`, `Add files via upload`, `WIP`
- One logical change per commit. Body explains why when it is not obvious.
- Never use `--no-verify`, `--force`, or `--amend` on pushed commits without explicit approval.

## Merge conflicts
- Show both sides and who wrote each. Never resolve by taking only "ours" or "theirs" for teammate code. Ask the user.

## Before a public release
- A secret that was ever committed must be rotated. Do not rely on history rewriting.
- Add a `LICENSE` only after the team chooses one. Ask before creating it.
- Keep `.env.example` and `team.env.example` current with names only.
- Never commit real user data, even in fixtures or screenshots. Use fake data.
- Suggest enabling GitHub secret scanning, push protection, Dependabot, and branch protection with required review on `main`.
