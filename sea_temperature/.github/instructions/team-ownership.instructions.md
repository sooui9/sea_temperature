---
name: Team ownership
description: Use before creating, editing, deleting, moving, or formatting any file, and before git operations that touch others' work. Protects teammates' code from AI edits.
applyTo: "**"
---

# Team ownership rules

Four people build this repo. An AI edit that silently changes a teammate's code breaks their work and their trust. These rules win over anti-slop and refactoring instincts. On conflict with any other rule except security, this file wins; report the conflict.

## 1. Find the owner first
1. Look up the file in `docs/OWNERSHIP.md`.
2. Not listed: `git log --format=%an -- <file>`. The main author is the owner.
3. Co-authored or shared files: `git blame -L <start>,<end> <file>` on the exact lines you would change. Each line belongs to its author.
4. Compare with `git config user.name` and the aliases in `docs/OWNERSHIP.md`.
5. New file, untracked file, or the current user's own lines: yours. Anything else, including unknown: someone else's.

## 2. What you may do without asking
- Read, search, and run teammates' code.
- Import or call their functions and APIs as they are.
- Create new files in the current user's area.
- Edit the current user's own files and lines within the task.

## 3. What needs explicit approval
For code that belongs to someone else, do not do any of the following until the user approves that specific file and change:
- modify, delete, comment out, rename, or move code, files, tests, comments, or docs;
- reformat, reorder imports, rename variables, or change indentation;
- change function signatures, API routes, response shapes, DB queries, CSS class names, element IDs, or sessionStorage keys that their code relies on;
- edit their tests so that they pass.

How to ask:
```
[팀원 코드 수정 요청]
파일: insurance.html (담당: sooui9)
이유: 홈 화면에서 보험 카드로 넘어갈 때 species 값을 받아야 함
변경안: (diff 10줄 이내 요약)
대안: 내 파일에서 처리하는 방법 — (있으면 적기)
```
"Proceed" or general approval earlier in the session does not cover a new file or a new change. Ask again.

## 4. If approved
- Keep the change minimal and additive. Do not touch nearby lines.
- Preserve existing behavior unless the approval was for changing it.
- In the PR description, list each teammate file you changed and mention its owner for review.

## 5. Never, even with general approval
- Delete a teammate's file or a whole function, section, or test. The user must confirm that the owner agreed.
- Run repo-wide search-and-replace, formatters, or `--fix` linters on files outside the current user's area.
- Resolve a merge conflict by dropping one side. Show both sides and ask.
- Run `git reset --hard`, `git checkout -- <path>`, `git restore`, `git clean`, `git stash drop`, rebase of a shared branch, or force push.
- Change shared DB tables, data, or permissions created by others.

## 6. Shared files
`common.css`, `common.js`, `README.md`, `.gitignore`, `backend/backend/main.py`, `backend/backend/config.py`, `backend/backend/db.py`, and requirement files are used by everyone.
- Additive changes only (a new row, route registration, or variable), each one approved.
- Never remove or rewrite another person's lines in them.
- `common.css` and `common.js` (shared tab bar): change only through their maintainer listed in `docs/OWNERSHIP.md`. Do not override tab bar styles per page.

## 7. When you find a problem in others' code
Report it with file, line, and the reason. Do not fix it. Suggest the user tell the owner, or offer a fix the user can forward.

## 8. Report
At the end of a task that changed files, list every changed file with its owner, and mark teammates' files with the approval you received.
