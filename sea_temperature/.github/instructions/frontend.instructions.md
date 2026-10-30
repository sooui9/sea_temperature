---
name: HTML screens
description: Use when creating or editing the dashboard HTML screens (consult_home, farm_detail, sea_forecast, consult_status) or their side menu.
applyTo: "**/*.html,**/*.css,**/*.js"
---

# HTML screen conventions

## Structure
- One screen (feature) per HTML file, so each teammate connects only their own screen to data. A new screen is a new file, not a section inside someone else's file.
- A new screen must also be added to `SCREENS` in `backend/backend/main.py`, or the Render deploy will not serve it.
- Plain HTML/CSS/JS. No build tool, framework, or CDN dependency unless the user approves.
- Inside a file: `<style>` is design, `<section>` is screen content, `<script>` is behavior. Keep that split.
- Font "Noto Sans KR" stack and a visible `:focus-visible` outline, like the existing screens.

## Side menu
- Every screen has the same `<nav class="side" aria-label="화면 이동">` linking the four screens. When adding or renaming a screen, the menu in every screen file changes, so each owner must approve.

## Data between screens
- `localStorage` keys `heat-dashboard-office` (selected office) and `heat-dashboard-split-v1` are shared across screens. Do not rename a key or change its shape without approval from every screen owner.
- Deep links: `farm_detail.html?id=<household_id>`, `farm_detail.html#home|detail|forecast|consult`, `sea_forecast.html?region=<region>`.
- Do not change the `const API_BASE = …` line in any screen; it is set to work on both local and deployed addresses.
- Every data-driven view has loading, empty, error, and success states. Server down means sample data (SAMPLE) plus a visible warning, never silent fake data.

## Wording
- Insurance and support text never promises payment. Use "약관 조건 확인 필요", not "보상됩니다".
- Forecast values are references, not guarantees. Show the data source and update time.
- Write UI text in plain Korean. Avoid jargon or explain it.
