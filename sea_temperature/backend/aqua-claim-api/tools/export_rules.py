"""규칙 카탈로그를 검토용 CSV 로 내보낸다: python -m tools.export_rules tests/fixtures/coverages_all.json data/calc_rules.csv"""
import csv, json, sys
from app.rules import resolve

cov = json.load(open(sys.argv[1], encoding="utf-8"))
rows = []
for c in sorted(cov, key=lambda c: (c["product_id"], c["coverage_key"])):
    if c["effect"] != "보장추가":
        continue
    for obj in ("수산물", "시설물"):
        r = resolve(c["product_id"], c["coverage_key"], c["name"], c["contract_type"], obj)
        if r is None or r.object != obj:
            continue
        rows.append({"product_id": c["product_id"], "coverage_key": c["coverage_key"], "coverage_name": c["name"],
                     "contract_type": c["contract_type"], "object": obj, "method": r.method, "deductible": r.deductible,
                     "full_cover_ratio": r.full_cover_ratio, "min_amount": r.min_amount or "", "fixed_amount": r.fixed_amount or "",
                     "budget_plans": "Y" if r.budget_plans else "", "unfarmable": r.unfarmable or "",
                     "source": r.source, "interpretation": r.interpretation or ""})
with open(sys.argv[2], "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows))
