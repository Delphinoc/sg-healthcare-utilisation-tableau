# Singapore Public Healthcare Utilisation & Chronic Disease

**How has demand for Singapore's public outpatient services grown, how much of polyclinic work is chronic disease, and which weeks of acute polyclinic attendances fall outside their expected range?**

A SQL (DuckDB), Python and Tableau project on three Ministry of Health (MOH) open datasets. The SQL model validates the data and computes KPIs and weekly alert flags. The Tableau dashboard presents them across three pages: demand, chronic disease and weekly alerts. All results are descriptive.

**Dashboard:** _Tableau Public link to be added after publishing_ (see [`docs/tableau_build_guide.md`](docs/tableau_build_guide.md))

## Findings

Numbers come from [`reports/summary.json`](reports/summary.json) and the extracts in [`tableau/extracts/`](tableau/extracts/), and are pinned by tests.

### 1. Public outpatient demand (2006–2021)
- Polyclinic attendances grew **77.5%** from 2006 to 2019 (3.77M to 6.69M, about 4.5% a year). This was the fastest of the four care settings: A&E grew 59.8%, SOCs 45.8% and dental 27.7%.
- Polyclinics' share of public outpatient attendances rose from **42.3% (2006) to 47.4% (2019)**.
- In 2020, attendances fell in every setting: dental −34.5%, A&E −16.5%, SOCs −15.3% and polyclinics −10.4%.

### 2. Chronic disease in polyclinics (2006–2025)
- Hyperlipidaemia, hypertension and diabetes together made up **36%–42% of all polyclinic diagnoses** in every year, peaking at 41.8% in 2008. The figure was 36.1% in 2025.
- Hypertension's share fell steadily, from 17.2% to 12.5%. Hyperlipidaemia has been the top condition since 2012.
- Acute URTI fell from 8.6% of diagnoses (2019) to 3.6% (2021), during COVID-19 measures. That pushed the chronic share back up to 40.0% in 2020–2021.

### 3. Weekly alerts (2012–2022)
- Using a historical-limits rule (mean ± 2 SD of the same weeks in the previous five years), **40 to 46 of the 53 weeks in 2020** were below the expected range for each of URTI, diarrhoea, chickenpox and conjunctivitis. For URTI, the run started in the week of 29 March 2020.
- Acute diarrhoea was above its expected range in **20 weeks of 2018 and 24 of 2019**. The rule does not adjust for population growth, so part of this reflects the trend rather than outbreaks.

### 4. Data quality
Three issues were found and logged in [`tableau/extracts/dq_issues.csv`](tableau/extracts/dq_issues.csv):

| Record | Published value | Issue | Handling |
|---|---|---|---|
| Specialist Outpatient Clinics, 2014 | 453,085 | About 10% of the surrounding years (likely a dropped digit) | Kept; excluded from totals and growth |
| Public Sector Dental Clinics, 2017 | 106,708 | About 10% of the surrounding years | Kept; excluded from totals and growth |
| Chickenpox, 2014 | — | Two week-52 rows and no week 53 | Later row relabelled as week 53 |

## Data model

```
data/raw/*.csv  ──►  01_staging.sql   typed staging tables
                     02_dimensions.sql   care setting, condition, disease, epi-week calendar
                     03_facts.sql   validated facts, KPIs, alert flags, DQ log
                ──►  tableau/extracts/*.csv  ──►  scripts/build_workbook.py  ──►  tableau/*.twbx  ──►  Tableau Public
```

- **Facts:** `fct_outpatient_annual`, `fct_outpatient_year_total`, `fct_polyclinic_conditions`, `fct_chronic_share`, `fct_weekly_disease`, `fct_dq_issues`
- **Dimensions:** `dim_care_setting`, `dim_condition`, `dim_disease`, `dim_epi_week` (Sunday–Saturday epi weeks, including 53-week years)
- Every table, rule, KPI and extract column is documented in [`docs/data_dictionary.md`](docs/data_dictionary.md).

## Testing

`python -m pytest` runs 23 tests, which cover:
- unchanged raw files (SHA-256), row counts and unique keys
- the epi-week calendar
- the data-quality rules, including that the 2020 COVID dip is *not* flagged as an error
- KPI reconciliation against the raw files
- an independent pandas implementation of the weekly alert rule, which must match the SQL for all 2,557 rows
- that the committed extracts are current and that every extract column is documented

## How to reproduce

```bash
pip install -r requirements.txt
python scripts/build_model.py     # builds data/processed/sg_healthcare.duckdb and tableau/extracts/
python -m pytest
```
Then open `tableau/sg_healthcare_utilisation.twbx` in Tableau Public. To regenerate it, run `python scripts/build_workbook.py`. The manual build steps are in [`docs/tableau_build_guide.md`](docs/tableau_build_guide.md).

## Limitations

- These are aggregate public statistics. There are no patient-level, cost or outcome data, so the project measures **utilisation, not value or quality of care**.
- The outpatient file ends in 2021 and the weekly file ends in 2022.
- Top-4 shares are shares of diagnoses (several per visit are possible) and exclude preventive-care visits.
- The weekly alert rule is a screening flag, not a significance test. It does not adjust for trend or population growth, and the 2021–2022 baselines include COVID-19 years.
- The two suspected entry errors are inferred from the data, not confirmed by MOH.

## Data source and licence

Data: Ministry of Health, via [data.gov.sg](https://data.gov.sg), under the [Singapore Open Data Licence](https://data.gov.sg/open-data-licence):
[Outpatient Attendances](https://data.gov.sg/datasets/d_e818f045a9681df2db90a493803a60d2/view) ·
[Top 4 Conditions of Polyclinic Attendances](https://data.gov.sg/datasets/d_a1ab62d65ae87130925c1f52a1d0c79d/view) ·
[Average Daily Polyclinic Attendances for Selected Diseases](https://data.gov.sg/datasets/d_5d5508f1c954f5630d7b3aa7875d01f9/view).

Code: [MIT](LICENSE), © 2026 Delphino Chew Jing Cheng. This is a portfolio project, not affiliated with MOH.
