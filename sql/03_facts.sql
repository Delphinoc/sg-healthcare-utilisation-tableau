-- 03_facts.sql
-- Fact tables with data-quality handling and KPI columns.
-- Rules are fixed up front and documented in docs/data_dictionary.md.

------------------------------------------------------------------------------
-- 1. Annual outpatient attendances by care setting
--    DQ rule (neighbour ratio): a reported value is a suspected entry error when it
--    is below 50% or above 150% of the median of the other values in its centred
--    five-year window (y-2..y+2, itself excluded). The median keeps one bad value
--    from flagging its neighbours. Suspected errors are kept as reported but
--    excluded from validated values, totals and growth KPIs. Nothing is imputed.
------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fct_outpatient_annual AS
WITH checked AS (
    SELECT
        o.*,
        o.attendances / (
            SELECT MEDIAN(n.attendances)
            FROM stg_outpatient n
            WHERE n.care_setting = o.care_setting
              AND n.year BETWEEN o.year - 2 AND o.year + 2
              AND n.year <> o.year
        ) AS neighbour_ratio
    FROM stg_outpatient o
),
validated AS (
    SELECT
        year, care_setting, attendances AS attendances_reported,
        ROUND(neighbour_ratio, 3) AS neighbour_ratio,
        CASE WHEN neighbour_ratio < 0.5 OR neighbour_ratio > 1.5
             THEN 'Suspected entry error' ELSE 'OK' END AS dq_status,
        CASE WHEN neighbour_ratio < 0.5 OR neighbour_ratio > 1.5
             THEN NULL ELSE attendances END AS attendances_validated
    FROM checked
)
SELECT
    v.year,
    v.care_setting,
    d.care_setting_short,
    d.care_level,
    d.sort_order,
    v.attendances_reported,
    v.attendances_validated,
    v.neighbour_ratio,
    v.dq_status,
    ROUND(100.0 * (v.attendances_validated / LAG(v.attendances_validated) OVER w - 1), 2)
        AS yoy_change_pct,
    ROUND(100.0 * v.attendances_validated
          / FIRST_VALUE(v.attendances_validated) OVER (PARTITION BY v.care_setting ORDER BY v.year
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 1)
        AS index_2006_eq_100
FROM validated v
JOIN dim_care_setting d USING (care_setting)
WINDOW w AS (PARTITION BY v.care_setting ORDER BY v.year);

-- Year totals are only reported when all four settings pass validation.
CREATE OR REPLACE TABLE fct_outpatient_year_total AS
SELECT
    year,
    COUNT(*) FILTER (WHERE dq_status = 'OK')                         AS settings_validated,
    CASE WHEN COUNT(*) FILTER (WHERE dq_status = 'OK') = 4
         THEN SUM(attendances_validated) END                         AS total_attendances_validated,
    SUM(attendances_validated) FILTER (WHERE care_setting = 'Polyclinics')
        / NULLIF(CASE WHEN COUNT(*) FILTER (WHERE dq_status = 'OK') = 4
                      THEN SUM(attendances_validated) END, 0)        AS polyclinic_share
FROM fct_outpatient_annual
GROUP BY year;

------------------------------------------------------------------------------
-- 2. Polyclinic diagnoses: share of all diagnoses for the top-4 conditions
------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fct_polyclinic_conditions AS
SELECT
    p.year,
    p.condition,
    c.condition_short,
    c.condition_type,
    c.sort_order,
    p.pct_of_diagnoses,
    ROUND(p.pct_of_diagnoses - LAG(p.pct_of_diagnoses) OVER w, 2) AS pp_change_yoy,
    RANK() OVER (PARTITION BY p.year ORDER BY p.pct_of_diagnoses DESC) AS rank_in_year
FROM stg_polyclinic_conditions p
JOIN dim_condition c USING (condition)
WINDOW w AS (PARTITION BY p.condition ORDER BY p.year);

CREATE OR REPLACE TABLE fct_chronic_share AS
SELECT
    year,
    ROUND(SUM(pct_of_diagnoses) FILTER (WHERE condition_type = 'Chronic'), 2) AS chronic_pct_of_diagnoses,
    ROUND(SUM(pct_of_diagnoses) FILTER (WHERE condition_type = 'Acute'), 2)   AS acute_urti_pct_of_diagnoses
FROM fct_polyclinic_conditions
GROUP BY year;

------------------------------------------------------------------------------
-- 3. Weekly average daily polyclinic attendances, with alert flags
--    DQ: the source has two 2014-W52 Chickenpox rows and no 2014-W53 row (every
--    other disease has W53). The later row in file order is relabelled W53.
--
--    Alert rule (historical limits method): for disease d, year y, week w, the
--    baseline is every value for d in years y-5..y-1 and weeks w-2..w+2 (week 53
--    compared with weeks 51-53). Above expected: value > mean + 2 SD.
--    Below expected: value < mean - 2 SD. At least 15 baseline values (three prior
--    years) are needed, so alerts start in 2015 (2021 for HFMD).
------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fct_weekly_disease AS
WITH ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY epi_year, epi_week_num, disease ORDER BY source_row) AS dup_rank
    FROM stg_weekly
),
fixed AS (
    SELECT
        epi_year,
        CASE WHEN dup_rank = 2 AND disease = 'Chickenpox' AND epi_year = 2014 AND epi_week_num = 52
             THEN 53 ELSE epi_week_num END AS epi_week_num,
        disease,
        avg_daily_attendances,
        CASE WHEN dup_rank = 2 AND disease = 'Chickenpox' AND epi_year = 2014 AND epi_week_num = 52
             THEN 'Relabelled from duplicate 2014-W52 to missing 2014-W53' END AS dq_note
    FROM ranked
),
baseline AS (
    SELECT
        cur.epi_year, cur.epi_week_num, cur.disease,
        COUNT(hist.avg_daily_attendances)              AS baseline_n,
        AVG(hist.avg_daily_attendances)                AS baseline_mean,
        STDDEV_SAMP(hist.avg_daily_attendances)        AS baseline_sd
    FROM fixed cur
    LEFT JOIN fixed hist
      ON hist.disease = cur.disease
     AND hist.epi_year BETWEEN cur.epi_year - 5 AND cur.epi_year - 1
     AND hist.epi_week_num BETWEEN LEAST(cur.epi_week_num, 51) - 2 AND LEAST(cur.epi_week_num, 51) + 2
    GROUP BY 1, 2, 3
)
SELECT
    e.week_start,
    e.week_end,
    f.epi_year,
    f.epi_week_num,
    e.epi_week_label,
    ROUND(f.epi_year + (f.epi_week_num - 1) / 52.0, 4)     AS year_fraction,
    f.disease,
    d.disease_short,
    d.sort_order,
    f.avg_daily_attendances,
    b.baseline_n,
    ROUND(b.baseline_mean, 1)                              AS baseline_mean,
    ROUND(b.baseline_sd, 1)                                AS baseline_sd,
    CASE WHEN b.baseline_n >= 15 THEN ROUND(b.baseline_mean + 2 * b.baseline_sd, 1) END AS upper_limit,
    CASE WHEN b.baseline_n >= 15 THEN ROUND(GREATEST(b.baseline_mean - 2 * b.baseline_sd, 0), 1) END AS lower_limit,
    CASE WHEN b.baseline_n >= 15 AND b.baseline_mean > 0
         THEN ROUND(f.avg_daily_attendances / b.baseline_mean, 3) END AS ratio_to_expected,
    CASE
        WHEN b.baseline_n < 15 THEN 'No baseline'
        WHEN f.avg_daily_attendances > b.baseline_mean + 2 * b.baseline_sd THEN 'Above expected'
        WHEN f.avg_daily_attendances < b.baseline_mean - 2 * b.baseline_sd THEN 'Below expected'
        ELSE 'Within expected'
    END                                                    AS alert_status,
    f.dq_note
FROM fixed f
JOIN baseline b USING (epi_year, epi_week_num, disease)
JOIN dim_epi_week e USING (epi_year, epi_week_num)
JOIN dim_disease d USING (disease);

------------------------------------------------------------------------------
-- 4. Data-quality issue log (one row per issue, shown on the dashboard)
------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fct_dq_issues AS
SELECT
    'Outpatient attendances'                     AS dataset,
    care_setting || ', ' || year                 AS record,
    attendances_reported                         AS reported_value,
    'Value is ' || CAST(ROUND(neighbour_ratio * 100) AS INTEGER) || '% of the surrounding-year median' AS issue,
    'Ratio to median of years y-2..y+2 outside 50%-150%'           AS rule,
    'Kept as reported; excluded from validated values, totals and growth' AS handling
FROM fct_outpatient_annual
WHERE dq_status <> 'OK'
UNION ALL
SELECT
    'Weekly polyclinic attendances',
    disease || ', ' || epi_week_label,
    avg_daily_attendances,
    'Duplicate 2014-W52 row and missing 2014-W53 row',
    'One row per disease and epi week',
    'Later duplicate relabelled as 2014-W53'
FROM fct_weekly_disease
WHERE dq_note IS NOT NULL;
