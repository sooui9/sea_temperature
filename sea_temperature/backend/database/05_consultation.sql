-- Admin-only migration. Review and run as a role that can create tables in customer_service.
-- Consultation dashboard: contact order (n8n), current case status, append-only history.
-- Coverage status (none / no rider / covered) is derived from insurance_contracts/targets, not stored.
-- Existing customer_service tables and rows are never changed.
BEGIN;

-- Dummy regions so the dashboard's Hadong/Sacheon farms have a region_code.
-- Coordinates are placeholders, not verified farm locations.
-- region_id is GENERATED ALWAYS, so the identity sequence assigns it (14, 15 on the current DB).
INSERT INTO public.sigungu_area_coordinates
    (sigungu_name, area_name, latitude, longitude,
     coordinate_type, source_url, aquaculture_coordinate_verification)
VALUES
    ('하동군', '금남면', 34.9400, 127.8700, '가상 대표점(더미)', NULL, '미검증'),
    ('사천시', '서포면', 35.0100, 127.9900, '가상 대표점(더미)', NULL, '미검증')
ON CONFLICT (sigungu_name, area_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS customer_service.household_contacts (
    household_id integer PRIMARY KEY
        REFERENCES customer_service.fishery_households(household_id) ON DELETE CASCADE,
    phone_number varchar(11) NOT NULL CHECK (phone_number ~ '^010[0-9]{8}$'),
    sms_consent boolean NOT NULL DEFAULT false,
    consent_at timestamptz,
    consent_source varchar(10) CHECK (consent_source IN ('서면', '전화', '앱')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT sms_consent OR (consent_at IS NOT NULL AND consent_source IS NOT NULL))
);

-- Written by n8n per base_date; the dashboard only reads it.
CREATE TABLE IF NOT EXISTS customer_service.contact_queue (
    queue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    base_date date NOT NULL,
    household_id integer NOT NULL
        REFERENCES customer_service.fishery_households(household_id) ON DELETE CASCADE,
    rank integer NOT NULL CHECK (rank > 0),
    score integer NOT NULL,
    risk_stage smallint NOT NULL CHECK (risk_stage BETWEEN 0 AND 3),
    list_reason varchar(10) NOT NULL CHECK (list_reason IN ('위험 단계', '공식 특보', '판매 마감')),
    reason_text varchar(200),
    lead_mapping_id integer REFERENCES customer_service.household_species(mapping_id),
    score_detail jsonb,
    computed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (base_date, household_id),
    UNIQUE (base_date, rank)
);

CREATE TABLE IF NOT EXISTS customer_service.consult_cases (
    case_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id integer NOT NULL
        REFERENCES customer_service.fishery_households(household_id) ON DELETE CASCADE,
    season varchar(20) NOT NULL,
    status varchar(10) NOT NULL DEFAULT '미연락' CHECK (status IN
        ('미연락', '부재·재연락', '문자 발송', '상담 예약', '가입 완료', '안내 완료', '보류·거절')),
    next_contact_at timestamptz,
    last_contact_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (household_id, season),
    -- Target for consult_logs' composite FK so a log cannot point at another household's case.
    UNIQUE (case_id, household_id),
    CHECK (status NOT IN ('부재·재연락', '상담 예약') OR next_contact_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS consult_cases_status_idx ON customer_service.consult_cases(status);

-- Append-only: the API inserts one row per saved consultation and never updates it.
CREATE TABLE IF NOT EXISTS customer_service.consult_logs (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id bigint NOT NULL,
    household_id integer NOT NULL,
    contacted_at timestamptz NOT NULL DEFAULT now(),
    channel varchar(5) NOT NULL CHECK (channel IN ('전화', '문자', '방문', '창구')),
    result_status varchar(10) NOT NULL CHECK (result_status IN
        ('미연락', '부재·재연락', '문자 발송', '상담 예약', '가입 완료', '안내 완료', '보류·거절')),
    memo text,
    next_contact_at timestamptz,
    staff_name varchar(50),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (case_id, household_id)
        REFERENCES customer_service.consult_cases(case_id, household_id)
);

CREATE INDEX IF NOT EXISTS consult_logs_household_idx
    ON customer_service.consult_logs(household_id, contacted_at DESC);

-- One row per species (1 species = 1 contract) discussed in a consultation.
-- The API must check that mapping_id belongs to the log's household.
CREATE TABLE IF NOT EXISTS customer_service.consult_log_items (
    log_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    log_id bigint NOT NULL REFERENCES customer_service.consult_logs(log_id),
    mapping_id integer NOT NULL REFERENCES customer_service.household_species(mapping_id),
    result varchar(10) NOT NULL CHECK (result IN ('가입', '보류', '안내', '타 기관 가입')),
    insurance_id integer REFERENCES customer_service.insurance_contracts(insurance_id),
    UNIQUE (log_id, mapping_id)
);

-- Match existing customer_service ownership so nifs_team2 can manage these tables.
ALTER TABLE customer_service.household_contacts OWNER TO nifs_team2;
ALTER TABLE customer_service.contact_queue OWNER TO nifs_team2;
ALTER TABLE customer_service.consult_cases OWNER TO nifs_team2;
ALTER TABLE customer_service.consult_logs OWNER TO nifs_team2;
ALTER TABLE customer_service.consult_log_items OWNER TO nifs_team2;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    customer_service.household_contacts, customer_service.contact_queue,
    customer_service.consult_cases, customer_service.consult_logs,
    customer_service.consult_log_items
TO nifs_team1;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    customer_service.household_contacts, customer_service.contact_queue,
    customer_service.consult_cases, customer_service.consult_logs,
    customer_service.consult_log_items
TO nifs_team2;

COMMIT;
