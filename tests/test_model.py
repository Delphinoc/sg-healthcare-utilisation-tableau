"""Tests for the DuckDB model, the data-quality rules and the Tableau extracts.

The weekly alert rule is recomputed independently in pandas and compared with SQL.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_model  # noqa: E402

RAW = ROOT / "data" / "raw"
RAW_SHA256 = {
    "outpatient_attendances.csv": "7b81fdebd839336e9609a51836f17243aeec2aed7ee77e7ec972b06eb5896089",
    "top4_polyclinic_conditions.csv": "46e321089f7e300a7bfeba7792a7fc8165c007342c901a697ca9131ecc497b10",
    "weekly_polyclinic_attendances.csv": "315d3c92963b25e7c4593d95e46bd6ba41fe131ab79e6f4982d5ffd91c0a0ccf",
}


@pytest.fixture(scope="session")
def con(tmp_path_factory) -> duckdb.DuckDBPyConnection:
    db = tmp_path_factory.mktemp("db") / "test.duckdb"
    return build_model.build(RAW, db)


@pytest.fixture(scope="session")
def extracts(con, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("extracts")
    build_model.export(con, out)
    return out


def df(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


# --- Raw data ---------------------------------------------------------------

@pytest.mark.parametrize("fname,sha", RAW_SHA256.items())
def test_raw_files_unchanged(fname, sha):
    assert hashlib.sha256((RAW / fname).read_bytes()).hexdigest() == sha


def test_staging_row_counts(con):
    assert con.execute("SELECT COUNT(*) FROM stg_outpatient").fetchone()[0] == 64
    assert con.execute("SELECT COUNT(*) FROM stg_polyclinic_conditions").fetchone()[0] == 80
    assert con.execute("SELECT COUNT(*) FROM stg_weekly").fetchone()[0] == 2557


# --- Keys and dimensions ----------------------------------------------------

@pytest.mark.parametrize("table,keys", [
    ("fct_outpatient_annual", "year, care_setting"),
    ("fct_polyclinic_conditions", "year, condition"),
    ("fct_weekly_disease", "epi_year, epi_week_num, disease"),
    ("dim_epi_week", "epi_year, epi_week_num"),
])
def test_unique_keys(con, table, keys):
    dupes = con.execute(f"SELECT COUNT(*) FROM (SELECT {keys} FROM {table} GROUP BY ALL HAVING COUNT(*) > 1)").fetchone()[0]
    assert dupes == 0


def test_all_source_rows_match_dimensions(con):
    # Inner joins in 03_facts.sql must not drop any rows.
    assert con.execute("SELECT COUNT(*) FROM fct_outpatient_annual").fetchone()[0] == 64
    assert con.execute("SELECT COUNT(*) FROM fct_polyclinic_conditions").fetchone()[0] == 80
    assert con.execute("SELECT COUNT(*) FROM fct_weekly_disease").fetchone()[0] == 2557


def test_epi_weeks_start_sunday_and_are_contiguous(con):
    w = df(con, "SELECT week_start, week_end FROM dim_epi_week ORDER BY week_start")
    assert (pd.to_datetime(w.week_start).dt.dayofweek == 6).all()  # pandas: Sunday = 6
    gaps = pd.to_datetime(w.week_start).diff().dropna().dt.days
    assert (gaps == 7).all()
    weeks_per_year = df(con, "SELECT epi_year, COUNT(*) n FROM dim_epi_week GROUP BY 1").set_index("epi_year").n
    assert weeks_per_year[2014] == 53 and weeks_per_year[2020] == 53 and weeks_per_year[2019] == 52


# --- Data-quality rules -----------------------------------------------------

def test_outpatient_suspected_errors_are_exactly_two(con):
    flagged = df(con, "SELECT year, care_setting FROM fct_outpatient_annual WHERE dq_status <> 'OK' ORDER BY year")
    assert flagged.values.tolist() == [
        [2014, "Specialist Outpatient Clinics"],
        [2017, "Public Sector Dental Clinics"],
    ]


def test_flagged_values_excluded_but_kept(con):
    r = df(con, "SELECT * FROM fct_outpatient_annual WHERE dq_status <> 'OK'")
    assert r.attendances_validated.isna().all()
    assert r.attendances_reported.notna().all()
    totals = df(con, "SELECT year FROM fct_outpatient_year_total WHERE total_attendances_validated IS NULL ORDER BY year")
    assert totals.year.tolist() == [2014, 2017]


def test_covid_dip_is_not_flagged_as_error(con):
    r = df(con, "SELECT dq_status FROM fct_outpatient_annual WHERE year = 2020 AND care_setting_short = 'Dental'")
    assert r.dq_status.iloc[0] == "OK"


def test_chickenpox_duplicate_relabelled(con):
    r = df(con, """SELECT epi_week_num, avg_daily_attendances, dq_note FROM fct_weekly_disease
                   WHERE disease = 'Chickenpox' AND epi_year = 2014 AND epi_week_num >= 52 ORDER BY 1""")
    assert r.epi_week_num.tolist() == [52, 53]
    assert r.avg_daily_attendances.tolist() == [14, 19]
    assert r.dq_note.notna().tolist() == [False, True]


def test_dq_issue_log(con):
    assert con.execute("SELECT COUNT(*) FROM fct_dq_issues").fetchone()[0] == 3


# --- KPIs -------------------------------------------------------------------

def test_chronic_share_matches_raw(con):
    raw = pd.read_csv(RAW / "top4_polyclinic_conditions.csv")
    chronic = raw[raw.condition != "Acute Upper Respiratory Tract Infection including Influenza"]
    expected = chronic.groupby("year").percentage_diagnoses.sum().round(2)
    got = df(con, "SELECT year, chronic_pct_of_diagnoses FROM fct_chronic_share").set_index("year").chronic_pct_of_diagnoses
    pd.testing.assert_series_equal(got.sort_index(), expected.sort_index(), check_names=False)


def test_polyclinic_growth_summary(con):
    s = build_model.summary(con)
    assert s["polyclinic_attendances_2006"] == 3769989
    assert s["polyclinic_attendances_2019"] == 6691295
    assert s["polyclinic_growth_2006_2019_pct"] == 77.5


def test_yoy_matches_pandas(con):
    a = df(con, "SELECT year, care_setting, attendances_validated, yoy_change_pct FROM fct_outpatient_annual ORDER BY care_setting, year")
    exp = (a.groupby("care_setting").attendances_validated.pct_change(fill_method=None) * 100).round(2)
    np.testing.assert_allclose(a.yoy_change_pct.astype(float), exp.astype(float), equal_nan=True)


# --- Weekly alert rule: independent pandas implementation --------------------

def pandas_alerts(con) -> pd.DataFrame:
    w = df(con, "SELECT epi_year, epi_week_num, disease, avg_daily_attendances FROM fct_weekly_disease")
    rows = []
    for r in w.itertuples():
        wk = min(r.epi_week_num, 51)
        hist = w[(w.disease == r.disease)
                 & w.epi_year.between(r.epi_year - 5, r.epi_year - 1)
                 & w.epi_week_num.between(wk - 2, wk + 2)].avg_daily_attendances
        if len(hist) < 15:
            status = "No baseline"
        else:
            m, sd = hist.mean(), hist.std(ddof=1)
            v = r.avg_daily_attendances
            status = "Above expected" if v > m + 2 * sd else "Below expected" if v < m - 2 * sd else "Within expected"
        rows.append((r.epi_year, r.epi_week_num, r.disease, status))
    return pd.DataFrame(rows, columns=["epi_year", "epi_week_num", "disease", "status"])


def test_alert_status_matches_pandas(con):
    sql = df(con, "SELECT epi_year, epi_week_num, disease, alert_status FROM fct_weekly_disease")
    merged = sql.merge(pandas_alerts(con), on=["epi_year", "epi_week_num", "disease"])
    assert len(merged) == 2557
    assert (merged.alert_status == merged.status).all()


def test_alerts_start_after_three_baseline_years(con):
    first = df(con, """SELECT disease, MIN(epi_year) y FROM fct_weekly_disease
                       WHERE alert_status <> 'No baseline' GROUP BY 1""").set_index("disease").y
    assert first["HFMD"] == 2021
    assert first.drop("HFMD").eq(2015).all()


# --- Extracts and documentation ----------------------------------------------

def test_extracts_written(extracts):
    expected = {"outpatient_annual": 64, "polyclinic_conditions": 80, "weekly_alerts": 2557, "dq_issues": 3}
    for name, n in expected.items():
        assert len(pd.read_csv(extracts / f"{name}.csv")) == n


def test_committed_extracts_are_current(extracts):
    for f in extracts.glob("*.csv"):
        committed = ROOT / "tableau" / "extracts" / f.name
        assert committed.exists(), f"{f.name} missing; run scripts/build_model.py"
        pd.testing.assert_frame_equal(pd.read_csv(committed), pd.read_csv(f))


def test_data_dictionary_covers_every_extract_column(extracts):
    text = (ROOT / "docs" / "data_dictionary.md").read_text()
    for f in extracts.glob("*.csv"):
        for col in pd.read_csv(f, nrows=0).columns:
            assert f"`{col}`" in text, f"{f.name}.{col} not documented"
