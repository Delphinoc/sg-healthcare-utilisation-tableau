-- 02_dimensions.sql
-- Small conformed dimensions. Groupings are labels for reporting only.

CREATE OR REPLACE TABLE dim_care_setting AS
SELECT * FROM (VALUES
    ('A&E',                           'A&E',            'Emergency',             1),
    ('Specialist Outpatient Clinics', 'SOCs',           'Hospital outpatient',   2),
    ('Polyclinics',                   'Polyclinics',    'Primary care',          3),
    ('Public Sector Dental Clinics',  'Dental',         'Dental',                4)
) AS t(care_setting, care_setting_short, care_level, sort_order);

-- Chronic = long-term conditions managed in primary care (the Healthier SG focus).
CREATE OR REPLACE TABLE dim_condition AS
SELECT * FROM (VALUES
    ('Hyperlipidemia',                                              'Hyperlipidaemia', 'Chronic', 1),
    ('Hypertensive Disease',                                        'Hypertension',    'Chronic', 2),
    ('Diabetes Mellitus',                                           'Diabetes',        'Chronic', 3),
    ('Acute Upper Respiratory Tract Infection including Influenza', 'Acute URTI',      'Acute',   4)
) AS t(condition, condition_short, condition_type, sort_order);

CREATE OR REPLACE TABLE dim_disease AS
SELECT * FROM (VALUES
    ('Acute Upper Respiratory Tract infections', 'Acute URTI',      1),
    ('Acute Diarrhoea',                          'Acute Diarrhoea', 2),
    ('Acute Conjunctivitis',                     'Conjunctivitis',  3),
    ('Chickenpox',                               'Chickenpox',      4),
    ('HFMD',                                     'HFMD',            5)
) AS t(disease, disease_short, sort_order);

-- Epidemiological weeks run Sunday to Saturday. Week 1 is the first week with at
-- least four days in the calendar year (MMWR convention), so some years have 53 weeks.
CREATE OR REPLACE TABLE dim_epi_week AS
WITH years AS (
    SELECT DISTINCT epi_year FROM stg_weekly
),
week1 AS (
    SELECT
        epi_year,
        make_date(epi_year, 1, 1) AS jan1,
        CAST(dayofweek(make_date(epi_year, 1, 1)) AS INTEGER) AS jan1_dow   -- Sunday = 0
    FROM years
),
starts AS (
    SELECT
        epi_year,
        CASE WHEN jan1_dow <= 3 THEN jan1 - jan1_dow
             ELSE jan1 + (7 - jan1_dow) END AS week1_start,
        CASE WHEN next_dow <= 3 THEN next_jan1 - next_dow
             ELSE next_jan1 + (7 - next_dow) END AS next_week1_start
    FROM (
        SELECT *,
            make_date(epi_year + 1, 1, 1) AS next_jan1,
            CAST(dayofweek(make_date(epi_year + 1, 1, 1)) AS INTEGER) AS next_dow
        FROM week1
    )
)
SELECT
    s.epi_year,
    w.epi_week_num,
    printf('%d-W%02d', s.epi_year, w.epi_week_num)                 AS epi_week_label,
    CAST(s.week1_start + 7 * (w.epi_week_num - 1) AS DATE)         AS week_start,
    CAST(s.week1_start + 7 * (w.epi_week_num - 1) + 6 AS DATE)     AS week_end
FROM starts s
CROSS JOIN (SELECT CAST(range AS INTEGER) AS epi_week_num FROM range(1, 54)) AS w
WHERE s.week1_start + 7 * (w.epi_week_num - 1) < s.next_week1_start;
