-- 01_staging.sql
-- Typed, renamed copies of the three raw MOH files (loaded by scripts/build_model.py
-- as raw_outpatient, raw_top4 and raw_weekly). No values are changed here, only
-- names, types and keys. Data-quality handling happens in 03_facts.sql.

CREATE OR REPLACE TABLE stg_outpatient AS
SELECT
    CAST(year AS INTEGER)            AS year,
    CAST(type AS VARCHAR)            AS care_setting,
    CAST(count AS BIGINT)            AS attendances
FROM raw_outpatient;

CREATE OR REPLACE TABLE stg_polyclinic_conditions AS
SELECT
    CAST(year AS INTEGER)                 AS year,
    CAST(condition AS VARCHAR)            AS condition,
    CAST(percentage_diagnoses AS DOUBLE)  AS pct_of_diagnoses
FROM raw_top4;

-- Weekly file: epi_week is 'YYYY-Www'. source_row keeps the file order so the
-- duplicated 2014-W52 Chickenpox row can be identified deterministically.
CREATE OR REPLACE TABLE stg_weekly AS
SELECT
    source_row,
    CAST(epi_week AS VARCHAR)                    AS epi_week_label,
    CAST(substr(epi_week, 1, 4) AS INTEGER)      AS epi_year,
    CAST(substr(epi_week, 7, 2) AS INTEGER)      AS epi_week_num,
    CAST(disease AS VARCHAR)                     AS disease,
    CAST("no._of_cases" AS INTEGER)              AS avg_daily_attendances
FROM raw_weekly;
