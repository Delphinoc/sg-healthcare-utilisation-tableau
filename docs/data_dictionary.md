# Data dictionary and KPI definitions

## Sources

All three files are Ministry of Health (MOH) datasets from data.gov.sg, used under the [Singapore Open Data Licence](https://data.gov.sg/open-data-licence). They are stored unchanged in `data/raw/` (SHA-256 checksums are pinned in `tests/test_model.py`).

| File | data.gov.sg dataset | Grain | Coverage |
|---|---|---|---|
| `outpatient_attendances.csv` | [Outpatient Attendances (A&E, SOCs, Polyclinics, Dental)](https://data.gov.sg/datasets/d_e818f045a9681df2db90a493803a60d2/view) | year × care setting | 2006–2021 |
| `top4_polyclinic_conditions.csv` | [Top 4 Conditions of Polyclinic Attendances](https://data.gov.sg/datasets/d_a1ab62d65ae87130925c1f52a1d0c79d/view) | year × condition | 2006–2025 |
| `weekly_polyclinic_attendances.csv` | [Average Daily Polyclinic Attendances for Selected Diseases](https://data.gov.sg/datasets/d_5d5508f1c954f5630d7b3aa7875d01f9/view) | epi week × disease | 2012–2022 (HFMD from 2018) |

MOH notes for the top-4 file: the ranking excludes well patients attending for preventive care (e.g. screening, immunisation) and counts multiple diagnoses in a single attendance. Shares are therefore **shares of diagnoses, not of patients or visits**.

## Model layers

| Layer | Tables | Built by |
|---|---|---|
| Staging | `stg_outpatient`, `stg_polyclinic_conditions`, `stg_weekly` | `sql/01_staging.sql` (types and names only) |
| Dimensions | `dim_care_setting`, `dim_condition`, `dim_disease`, `dim_epi_week` | `sql/02_dimensions.sql` |
| Facts | `fct_outpatient_annual`, `fct_outpatient_year_total`, `fct_polyclinic_conditions`, `fct_chronic_share`, `fct_weekly_disease`, `fct_dq_issues` | `sql/03_facts.sql` |
| Extracts | `tableau/extracts/*.csv` | `scripts/build_model.py` |

## Data-quality rules

| Rule | Applies to | Result | Handling |
|---|---|---|---|
| **Neighbour ratio:** value / median of the same setting's other values in years y-2..y+2 must be within 50%–150% | Outpatient attendances | 2 failures: SOCs 2014 (453,085) and Dental 2017 (106,708), each about 10% of the surrounding median, consistent with a dropped digit | Kept as reported; `attendances_validated` is blank, so the year is excluded from totals, growth and shares. Not imputed. |
| **Unique key:** one row per disease and epi week | Weekly attendances | Chickenpox has two 2014-W52 rows and no 2014-W53 row (all other diseases have W53) | The later row in file order is relabelled 2014-W53 and noted in `dq_note` |
| **Calendar:** epi weeks run Sunday–Saturday; week 1 is the first week with ≥4 days in the year | Weekly attendances | 2014 and 2020 have 53 weeks, matching the source | `week_start` derived in `dim_epi_week` |

The 2020 drops (e.g. Dental −34%) pass the neighbour-ratio rule because they are real COVID-19 effects, not entry errors.

## KPI definitions

| KPI | Definition |
|---|---|
| Validated attendances | Reported attendances for a care setting and year, blank when the neighbour-ratio rule fails |
| YoY change % | 100 × (validated this year / validated last year − 1); blank if either year is blank |
| Index (2006 = 100) | 100 × validated attendances / the setting's 2006 value |
| Total public outpatient attendances | Sum of the four settings, reported only when all four pass validation |
| Polyclinic share | Polyclinic attendances / total public outpatient attendances |
| Chronic share of diagnoses | Sum of the % of polyclinic diagnoses for hyperlipidaemia, hypertension and diabetes |
| Expected range (weekly) | Historical limits method: mean ± 2 SD of the same disease's values in the previous 5 years, weeks w−2..w+2 (week 53 uses weeks 49–53). Needs ≥15 baseline values (three prior years) |
| Ratio to expected | Weekly average daily attendances / baseline mean, so diseases of different sizes share one scale |
| Alert status | `Above expected` / `Below expected` when the week is outside the expected range, `Within expected` otherwise, `No baseline` before three prior years exist |

The alert rule is a **screening flag** for review, not a statistical test of an outbreak. Baselines for 2020–2022 include pre-COVID years, so pandemic weeks appear as `Below expected`.

## Extract columns

### `outpatient_annual.csv` (one row per year × care setting, 64 rows)

| Column | Description |
|---|---|
| `year` | Calendar year |
| `care_setting` | MOH care setting name |
| `care_setting_short` | Short label for charts |
| `care_level` | Emergency, Hospital outpatient, Primary care or Dental |
| `sort_order` | Display order for care settings |
| `attendances_reported` | Attendances exactly as published |
| `attendances_validated` | Reported attendances, blank if the neighbour-ratio rule fails |
| `yoy_change_pct` | Year-on-year change in validated attendances, % |
| `index_2006_eq_100` | Validated attendances indexed to 2006 = 100 |
| `neighbour_ratio` | Reported value / median of the setting's other values in years y-2..y+2 |
| `dq_status` | `OK` or `Suspected entry error` |
| `year_total_validated` | Total public outpatient attendances for the year (blank if any setting failed validation) |
| `year_polyclinic_share` | Polyclinic share of the year total (0–1) |

### `polyclinic_conditions.csv` (one row per year × condition, 80 rows)

| Column | Description |
|---|---|
| `year` | Calendar year |
| `condition` | MOH condition name |
| `condition_short` | Short label for charts |
| `condition_type` | `Chronic` (hyperlipidaemia, hypertension, diabetes) or `Acute` (URTI) |
| `sort_order` | Display order for conditions |
| `pct_of_diagnoses` | % of all polyclinic diagnoses |
| `pp_change_yoy` | Change from the previous year, percentage points |
| `rank_in_year` | Rank among the four conditions in that year |
| `year_chronic_pct_of_diagnoses` | Chronic share of diagnoses for the year |

### `weekly_alerts.csv` (one row per epi week × disease, 2,557 rows)

| Column | Description |
|---|---|
| `week_start` | Sunday the epi week starts |
| `week_end` | Saturday the epi week ends |
| `epi_year` | Epidemiological year |
| `epi_week_num` | Epi week number (1–53) |
| `epi_week_label` | `YYYY-Www` label |
| `disease` | MOH disease name |
| `disease_short` | Short label for charts |
| `sort_order` | Display order for diseases |
| `avg_daily_attendances` | Average daily polyclinic attendances in the week |
| `baseline_n` | Number of historical values in the baseline |
| `baseline_mean` | Mean of the baseline values |
| `baseline_sd` | Sample standard deviation of the baseline values |
| `upper_limit` | baseline_mean + 2 × baseline_sd (blank without a baseline) |
| `lower_limit` | max(baseline_mean − 2 × baseline_sd, 0) (blank without a baseline) |
| `ratio_to_expected` | avg_daily_attendances / baseline_mean (1.0 = typical level; blank without a baseline) |
| `alert_status` | Above expected, Below expected, Within expected or No baseline |
| `dq_note` | Data-quality note for the row, if any |

### `dq_issues.csv` (one row per data-quality issue, 3 rows)

| Column | Description |
|---|---|
| `dataset` | Source dataset |
| `record` | Affected record |
| `reported_value` | Value as published |
| `issue` | What is wrong |
| `rule` | Rule that caught it |
| `handling` | How the model treats it |

## Change process

1. Replace a file in `data/raw/` with a newer download and update its checksum in `tests/test_model.py`.
2. Run `python scripts/build_model.py`, then `python -m pytest`.
3. Review any new rows in `dq_issues.csv` before refreshing the Tableau data sources.
