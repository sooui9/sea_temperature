# Reference log

One row per design reference actually used. Analyze patterns and rebuild independently; never copy. See `DESIGN.md` section 12.

Verification status: `read` = content actually read; `partial` = only part read; `unverified` = not read, nothing may be claimed from it.

## Setup-time official references

| Reference | URL | Intended use | Verification status | Notes |
|---|---|---|---|---|
| UI UX Pro Max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | Pattern search, palette and type suggestions, a11y/UX review, anti-pattern detection | partial | Only the repo description was readable; README, install steps, and license not read. Not installed in this project. Output is a candidate, never an approved rule. |
| Refero Styles | https://styles.refero.design/ | Study of real product design, layout, hierarchy, flows | partial | Only the landing page was read. Reuse terms of individual styles and images not checked. No scraping or redistribution of originals. |
| Awesome DESIGN.md | https://github.com/VoltAgent/awesome-design-md | How DESIGN.md files are structured, token layout, agent-readable docs | unverified | Fetch was blocked at setup time. Nothing was learned from it. Its documents are not adopted as this project's design. |

## Reference entries

| Service | Source URL | Pattern referenced | Why chosen | Part to redesign independently | Status | Date |
|---|---|---|---|---|---|---|
| sinuSHOE | 사용자 제공 `sinuSHOE-feature-main.zip`, `src/Detail.js` | 커서를 따르는 원형 확대 영역(1.8배, 240px) | 사용자 지정 참고 자료 | 이미지 전용 React 컴포넌트 대신 대시보드 DOM을 격리 복제하여 글자·이미지·차트 확대; 원본 코드·이미지 미사용 | read (해당 컴포넌트 사용 부분) | 2026-10-28 |
