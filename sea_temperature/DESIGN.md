# DESIGN.md

Single source of truth for design identity and shared design rules.

Status: DRAFT. Any value marked `UNDECIDED` is NOT approved. Do not pick, hard-code, or "temporarily" use it; propose options and wait for user approval.
Existing approved design system: none found at setup time.
Precedence: `AGENTS.md`, security, and Git rules win over this file. Report conflicts instead of resolving them silently.

## 1. Product and users
- Purpose: UNDECIDED
- Primary users: UNDECIDED

## 2. Principles
- Purpose before trend. Function and information importance drive visual hierarchy.
- Analyze and re-interpret references; never copy them.
- Every decoration has a stated reason (see section 11).
- Repeated elements become shared components.
- Consistency and usability together. Accessibility, responsiveness, readability, and performance are baseline quality, not extras.
- Never present a non-functional interface as a working feature.

### UX priority
Higher items are never sacrificed for lower ones:
1. User goal achievement
2. Usability and accessibility
3. Information structure and user flow
4. Interaction and state design
5. Visual finish
6. Decoration and visual effects

This is not a mandate for simplicity. Complex tasks may need dense information and many functions; justify density by the task, not by taste.

### UX rules
- Goal definition: before designing a new screen or core flow, state the target user, user goal, entry path, completion criterion, and cancel and failure paths. While section 1 is `UNDECIDED`, mark the user assumption `UNVERIFIED`; do not use it to fill section 1.
- Minimal effort: remove inputs and clicks that are not needed. Never ask again for information already provided in the flow. If many steps are unavoidable, state why.
- Error recovery: tell the user what happened and what to do next. Preserve entered data where possible. Give destructive actions confirmation or undo proportional to the risk. Never expose internal error causes or whether an account exists.
- First-time clarity: a first-time user can tell what the screen is for and what to do next. Add brief explanation or contextual help only where needed.
- Flow over screen: evaluate the whole flow, not only single screens. Check for repeated entry, needless navigation, dead ends, and hard-to-recover paths.
- Evidence levels: label every UX conclusion `TESTED` (method, participants, and date recorded), `EXPERT JUDGMENT` (expert opinion or guideline-based), or `UNVERIFIED` (insufficient basis). A tool or reference recommendation is at most `EXPERT JUDGMENT`; never call a design validated because a tool suggested it.
- Verifiable UX: each core flow names a validation method (task test, heuristic review, accessibility check, or error-recovery scenario test). A check that was not run is never reported as PASS.

## 3. Hierarchy and layout
- Importance maps to size, contrast, and position. One primary action per view.
- Layout system and grid: UNDECIDED
- Do not wrap every block in a card. Use cards only for discrete, repeated, or actionable items.
- Do not reuse one identical layout on every screen.

## 4. Color
- Brand, neutral, and semantic (success/warning/error/info) palettes: UNDECIDED
- Define colors as role-based tokens; components never hold raw color values.
- Contrast: text 4.5:1 (large text 3:1); UI component boundaries and focus indicators 3:1.
- Color is never the only carrier of meaning.
- No gradients, glow, or glass effects without justification (section 11).

## 5. Typography
- Font family, scale, weights, minimum body size: UNDECIDED
- A font must pass the license check (section 12) before adoption.
- Text must survive 200% browser zoom and user text resizing without clipping.

## 6. Spacing and grid
- Base unit and spacing scale: UNDECIDED
- Once decided, use only scale values; no ad-hoc pixel values.

## 7. Components
- Style family, border radius, shadow, icon set: UNDECIDED
- Button: verb-first label; visible focus; target at least 24x24 CSS px.
- Input: persistent visible label (not placeholder-only); error text next to the field and programmatically associated.
- Card: see section 3.
- Modal: only when interruption is required; trap focus, close on Esc, restore focus on close.

## 8. States
- Every data-driven view defines: loading, empty, error, success. Interactive elements define: hover, focus, active, disabled.
- Use realistic content and data, not lorem ipsum or perfect placeholder data.

## 9. Responsive and accessibility
- Target: WCAG 2.2 AA.
- Design mobile as mobile, not a shrunken desktop. Content reflows at 320 CSS px width without horizontal scroll.
- Full keyboard operation with visible focus order. No content overflow or layout breakage.
- Breakpoints: UNDECIDED

## 10. Motion
- Motion only to explain state change or causality. No decorative looping animation.
- Respect `prefers-reduced-motion`.
- Durations and easing: UNDECIDED

## 11. Anti-patterns and justification gate
Watch for: unrequested purple/pink gradients; needless glassmorphism, neon, heavy shadows; everything-in-a-card; meaningless icons or animation; oversized hero and excess whitespace; dashboards that show form without function; generic SaaS look unrelated to the product; low contrast or tiny text; shrunken-desktop mobile UI; identical layout on every screen.

These are not banned outright. Adopt one only if you can answer all five:
1. Why is this element needed?
2. How does it help the user?
3. Is there a simpler alternative?
4. Does it match this project's identity?
5. Which reference or principle supports it?

If any answer is weak, defer or simplify the element.

## 12. References and licensing
- References: study patterns, rebuild independently. Log each in `docs/design/REFERENCE_LOG.md`.
- Forbidden: unauthorized crawling, redistributing original images or screenshots, copying protected designs, shipping assets of unconfirmed rights.
- Third-party DESIGN.md files and tool recommendations (for example UI UX Pro Max) are candidates, never auto-approved rules.
- Every asset (icon, image, font, illustration, animation, code) needs a row in `docs/design/ASSET_LICENSES.md` before use. Unknown license means not approved. Free does not mean commercial use is allowed. AI-generated assets also need review.
- Never state "no legal issue" without real legal review.

## 13. Change and approval
- Turning an `UNDECIDED` value into a decision requires explicit user approval; record it in the log below.
- Quality checks: `docs/design/DESIGN_QA.md`.
- When per-page rules become necessary, split into `design-system/` (shared MASTER plus page-level differences). Do not create it before then.

## Observed in code (not approved)
Values already used in the screens. Reuse them for consistency; they become decisions only after the user approves and they move to the log below.

| Item | Observed value | Where |
|---|---|---|
| Product name | 우리 바다 안심도우미 | `common.css`, `common.js` header |
| Tab bar design baseline | 홈 화면 v2 | `home_test.html` |
| Font | "Noto Sans KR", system Korean fallbacks | `common.css` |
| Active / accent color | `#1f5ae0` on `#e8effd` | `common.css` tokens `--tabbar-active*` |
| Content max width | 420px | `common.css` `.tabbar` |
| Focus outline | 3px `#93b4f5`, offset 2px | `common.css` |

## Approved values log
| Date | Item | Value | Approved by |
|---|---|---|---|
| 2026-10-28 | Font | Noto Sans KR (400·500·700), sizes 11·12·13·14·15·16·20·26px | sooui9 |
| 2026-10-28 | Accent color | `#007F98` (soft `#E0F2F5`) | sooui9 |
| 2026-10-28 | Side menu | background `#017896`, white text; current page white with `#007F98` text | sooui9 |
| 2026-10-28 | Neutral colors | text `#334155` / `#475569` / `#64748B`, line `#E2E8F0`, input line `#CBD5E1`, page `#F4F5F7`, box `#F7F8FA` | sooui9 |
| 2026-10-28 | Success color | `#157C3C` on `#EAF5EF` | sooui9 |
| 2026-10-28 | Border radius | cards, buttons, inputs, popups 6px; status badges 3px; chips pill | sooui9 |
