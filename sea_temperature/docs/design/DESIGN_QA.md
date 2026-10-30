# Design QA

Checklist for reviewing a design or UI. Criteria come from `DESIGN.md`.

Reporting rule: mark each item `automated` (tool run, output shown), `manual` (human judgment), or `not run`. Never report a pass for `not run`.

## Verdict
- PASS: all items checked, none failed.
- CONDITIONAL: no failures, but some items `not run` or open questions remain; list them.
- FAIL: any failed item, an unapproved `UNDECIDED` value used, or an asset without license approval.

## 1. AI slop detection (manual)
- [ ] Each item in `DESIGN.md` section 11 checked; any used has a written answer to the five questions.
- [ ] No decoration without a reason; no generic look unrelated to the product.
- [ ] No interface presented as functional when it is not.

## 2. Hierarchy and consistency (manual)
- [ ] Visual hierarchy matches information importance; one primary action per view.
- [ ] Spacing, alignment, and components consistent; repeated elements are shared components.
- [ ] No lower-priority element (visual finish, decoration) undermines a higher-priority goal (`DESIGN.md` section 2, UX priority).

## 3. Accessibility, WCAG 2.2 AA (mix)
- [ ] Contrast: text 4.5:1 (large 3:1); UI boundaries and focus 3:1 (automated checker plus manual spot check).
- [ ] Full keyboard operation, visible focus, logical order (manual).
- [ ] Form fields have visible labels and associated errors; color is not the only signal (manual).
- [ ] Automated accessibility scan run on key pages (automated; tool and output recorded).
- [ ] `prefers-reduced-motion` respected (manual or automated).

## 4. Responsive and robustness (manual unless tooling exists)
- [ ] Usable at 320 CSS px width without horizontal scroll; at 200% zoom without clipping.
- [ ] No overflow or broken layout with long text and realistic data.
- [ ] Loading, empty, error, and success states exist for data-driven views.

## 5. Reference similarity (manual)
- [ ] Each reference is logged in `REFERENCE_LOG.md` with the independently redesigned part named.
- [ ] No layout, imagery, wording, or branding copied closely enough to be mistaken for the source.

## 6. Licensing (manual)
- [ ] Every asset has a row in `ASSET_LICENSES.md` with status `approved`.
- [ ] No third-party logos or distinctive visuals reproduced.

## 7. Performance (automated where possible)
- [ ] No unnecessary packages or heavy visual effects added; build or audit output attached if available.

## 8. UX flow and validation (manual unless a tool or test is recorded)
- [ ] Target user, user goal, entry path, completion criterion, and cancel and failure paths are defined for each new screen or core flow; if `DESIGN.md` section 1 is `UNDECIDED`, the user assumption is marked `UNVERIFIED`.
- [ ] A completion path and a failure or cancel path both exist and were walked through end to end.
- [ ] No unnecessary input, click, or step; no re-asking for information already provided; any long flow states why.
- [ ] Errors state what happened and the next action; entered data is preserved; destructive actions have proportional confirmation or undo; no internal causes or account existence exposed.
- [ ] A first-time user can tell the screen's purpose and the next action.
- [ ] Each UX conclusion is labeled `TESTED` (method, participants, date), `EXPERT JUDGMENT`, or `UNVERIFIED`; tool output counts at most as `EXPERT JUDGMENT`.
- [ ] Each core flow names a validation method; the report states which were actually run, and the rest stay `not run`.
