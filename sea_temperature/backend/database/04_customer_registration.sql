-- Admin-only migration. Review and run as the customer_service schema owner.
-- Existing species and coordinate tables and rows are never changed.
-- Relationships: customers 1:N farms, farms N:M species, farms N:1 coordinates.
-- Coordinates use their existing (sigungu_name, area_name) primary key.
-- region_id is an API lookup ID; it is not unique in the inspected schema.
-- Assign the backend account's privileges separately; do not use browser DB access.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT region_id FROM public.sigungu_area_coordinates
        GROUP BY region_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Coordinate region_id values must be unique before enabling registration';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS customer_service.customers (
    customer_id text PRIMARY KEY DEFAULT ('C-' || gen_random_uuid()::text),
    membership_status text NOT NULL DEFAULT 'guest'
        CHECK (membership_status IN ('guest', 'member')),
    name varchar(100),
    birth_date date,
    phone_number varchar(11) UNIQUE CHECK (phone_number ~ '^010[0-9]{8}$'),
    password_hash text,
    phone_verified_at timestamptz,
    registered_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (membership_status <> 'member' OR
        (name IS NOT NULL AND birth_date IS NOT NULL AND phone_number IS NOT NULL
         AND password_hash IS NOT NULL AND registered_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS customer_service.farms (
    farm_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id text NOT NULL REFERENCES customer_service.customers(customer_id),
    region_id bigint NOT NULL,
    sigungu_name text NOT NULL,
    town_name text NOT NULL,
    farming_method text NOT NULL CHECK (farming_method IN ('cage', 'land_based')),
    insurance_status text NOT NULL CHECK (insurance_status IN ('insured', 'uninsured', 'unknown')),
    high_temperature_coverage text CHECK (high_temperature_coverage IN ('yes', 'no', 'unknown')),
    total_premium_won bigint CHECK (total_premium_won BETWEEN 0 AND 1000000000000),
    premium_payment_method text CHECK (premium_payment_method IN ('once', 'twice', 'unknown')),
    insurance_start_month date CHECK (EXTRACT(DAY FROM insurance_start_month) = 1),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sigungu_name, town_name)
        REFERENCES public.sigungu_area_coordinates(sigungu_name, area_name),
    CHECK (insurance_status = 'insured' OR
        (high_temperature_coverage IS NULL AND total_premium_won IS NULL
         AND premium_payment_method IS NULL AND insurance_start_month IS NULL))
);

CREATE INDEX IF NOT EXISTS farms_customer_id_idx ON customer_service.farms(customer_id);

CREATE TABLE IF NOT EXISTS customer_service.farm_species (
    farm_id uuid NOT NULL REFERENCES customer_service.farms(farm_id) ON DELETE CASCADE,
    species_id bigint NOT NULL REFERENCES customer_service.species(species_id),
    PRIMARY KEY (farm_id, species_id)
);

CREATE TABLE IF NOT EXISTS customer_service.guest_sessions (
    session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id text NOT NULL REFERENCES customer_service.customers(customer_id),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS guest_sessions_customer_id_idx
    ON customer_service.guest_sessions(customer_id);

COMMIT;
