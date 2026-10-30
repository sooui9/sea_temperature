-- 적용가격(수협 공시) 테이블. insurance 스키마에 둔다.
-- 적재: psql 에서 아래 \copy 두 줄 실행 (data/ 의 CSV, UTF-8 BOM 포함이어도 됨)

CREATE TABLE IF NOT EXISTS insurance.insurance_applied_price (
    id             bigserial PRIMARY KEY,
    notice_month   varchar(7)  NOT NULL,              -- 공시월 '2026-10'
    section        text        NOT NULL,              -- 공시 섹션명 (예: 해상가두리어류/참돔)
    product_id     bigint      NOT NULL REFERENCES insurance.insurance_products(product_id),
    species_id     integer     NOT NULL REFERENCES customer_service.fish_species(species_id),
    variant        text,                              -- 식용/먹이용, 조기산/만기산, 양성기간 등
    region_scheme  varchar(10) NOT NULL,              -- 해수면 | 내수면 | 군 | ALL | 미확인
    region_no      text        NOT NULL,              -- '7','8' 또는 '전권역'
    region_label   text        NOT NULL,              -- 원문 표기
    weight_min_g   numeric,                           -- 'Ng 이상' 하한, 체중 구간 없는 품목은 NULL
    size_label     text,                              -- 굴 수하연 길이 등
    month          smallint CHECK (month BETWEEN 1 AND 12),
    price          numeric     NOT NULL,
    unit           varchar(20) NOT NULL,              -- KRW_PER_KG | KRW_PER_FISH | KRW_PER_LINE | KRW_PER_BOOK | KRW_PER_HA
    valid_from     date,
    valid_to       date,
    note           text,
    source         text
);

CREATE INDEX IF NOT EXISTS ix_applied_price_lookup
    ON insurance.insurance_applied_price (product_id, species_id, region_no, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS insurance.insurance_applied_price_formula (
    id            bigserial PRIMARY KEY,
    section       text    NOT NULL,
    product_id    bigint  NOT NULL REFERENCES insurance.insurance_products(product_id),
    variant       text    NOT NULL,
    applies       text,                               -- 적용 시기 설명
    formula       text    NOT NULL,                   -- 원문 산식
    base_price    numeric,                            -- 기준가 (숫자로 확정된 경우)
    period_end    text,                               -- 잔여일수 기준 종료일 'MM-DD'
    floor         text,                               -- 최저한도 (예: 종묘가격, 금액 미공시)
    region_label  text,
    valid_from    date,
    valid_to      date,
    source        text
);

-- \copy insurance.insurance_applied_price (notice_month,section,product_id,species_id,variant,region_scheme,region_no,region_label,weight_min_g,size_label,month,price,unit,valid_from,valid_to,note,source) FROM 'data/applied_price_r7_r8.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
-- \copy insurance.insurance_applied_price_formula (section,product_id,variant,applies,formula,base_price,period_end,floor,region_label,valid_from,valid_to,source) FROM 'data/applied_price_formula.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
