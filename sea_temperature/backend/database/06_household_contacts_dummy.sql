-- Dummy data for the consultation dashboard demo. Never run on a database with real customers.
-- Numbers use the unassigned 010-0000-xxxx block so they cannot reach a real person.
-- About 1 in 7 households has no consent; every 25th has no number at all.
BEGIN;

UPDATE customer_service.fishery_households
SET phone_number   = CASE WHEN household_id % 25 = 0 THEN NULL
                          ELSE '0100000' || lpad((household_id % 10000)::text, 4, '0') END,
    sms_consent    = household_id % 25 <> 0 AND household_id % 7 <> 0,
    sms_consent_at = CASE WHEN household_id % 25 <> 0 AND household_id % 7 <> 0
                          THEN timestamptz '2026-03-01 09:00+09' + (household_id % 60) * interval '1 day' END;

COMMIT;
