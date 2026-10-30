---
name: graphify
description: Use only when graphify-out/graph.json exists, before exploring the codebase or answering architecture questions.
---

# graphify knowledge graph

Applies only if `graphify-out/graph.json` exists. If it does not, ignore this file and search normally.

Before using search, read, or terminal tools to explore the codebase, run graphify first:
- `graphify query "<question>"`: scoped subgraph for any codebase or architecture question
- `graphify path "<A>" "<B>"`: dependency path between two symbols
- `graphify explain "<concept>"`: all nodes related to a concept

Include this rule in every subagent prompt that explores code. Do not skip graphify because files are "already known"; the graph shows cross-file dependencies and inferred edges that text search misses.

Read files directly only when:
1. graphify has already oriented you and you need to modify or debug specific lines, or
2. `graphify-out/graph.json` does not exist.

- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review when query/path/explain are not enough.
- After modifying code files, run `graphify update .` to keep the graph current.
