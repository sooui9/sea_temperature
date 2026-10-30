-- Admin-only migration. Review and run as a role that owns customer_service.fishery_households.
-- Contact and SMS consent live on the household row; customer_service.household_contacts stays unused.
BEGIN;

ALTER TABLE customer_service.fishery_households
    ADD COLUMN IF NOT EXISTS phone_number varchar(11) CHECK (phone_number ~ '^010[0-9]{8}$'),
    ADD COLUMN IF NOT EXISTS sms_consent boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS sms_consent_at timestamptz;

-- Consent must be provable: a number and the time it was given.
ALTER TABLE customer_service.fishery_households
    DROP CONSTRAINT IF EXISTS fishery_households_sms_consent_check,
    ADD CONSTRAINT fishery_households_sms_consent_check
        CHECK (NOT sms_consent OR (phone_number IS NOT NULL AND sms_consent_at IS NOT NULL));

COMMIT;
