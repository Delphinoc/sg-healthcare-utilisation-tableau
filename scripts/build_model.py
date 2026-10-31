"""Build the DuckDB model and export Tableau-ready CSV extracts.

Usage:
    python scripts/build_model.py [--raw data/raw] [--db data/processed/sg_healthcare.duckdb]
                                  [--out tableau/extracts]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = ["01_staging.sql", "02_dimensions.sql", "03_facts.sql"]

RAW_FILES = {
    "raw_outpatient": "outpatient_attendances.csv",
    "raw_top4": "top4_polyclinic_conditions.csv",
    "raw_weekly": "weekly_polyclinic_attendances.csv",
}

# Tableau extracts: one flat file per dashboard page plus the DQ log.
EXTRACTS = {
    "outpatient_annual": """
        SELECT a.year, a.care_setting, a.care_setting_short, a.care_level, a.sort_order,
               a.attendances_reported, a.attendances_validated, a.yoy_change_pct,
               a.index_2006_eq_100, a.neighbour_ratio, a.dq_status,
               t.total_attendances_validated AS year_total_validated,
               ROUND(t.polyclinic_share, 4)  AS year_polyclinic_share
        FROM fct_outpatient_annual a
        JOIN fct_outpatient_year_total t USING (year)
        ORDER BY a.year, a.sort_order""",
    "polyclinic_conditions": """
        SELECT p.year, p.condition, p.condition_short, p.condition_type, p.sort_order,
               p.pct_of_diagnoses, p.pp_change_yoy, p.rank_in_year,
               c.chronic_pct_of_diagnoses AS year_chronic_pct_of_diagnoses
        FROM fct_polyclinic_conditions p
        JOIN fct_chronic_share c USING (year)
        ORDER BY p.year, p.sort_order""",
    "weekly_alerts": """
        SELECT * FROM fct_weekly_disease ORDER BY week_start, sort_order""",
    "dq_issues": """
        SELECT * FROM fct_dq_issues ORDER BY dataset, record""",
}


def build(raw_dir: Path, db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    for table, fname in RAW_FILES.items():
        path = (raw_dir / fname).as_posix()
        if table == "raw_weekly":
            con.execute(
                f"CREATE TABLE {table} AS SELECT row_number() OVER () AS source_row, * "
                f"FROM read_csv('{path}', header=true, all_varchar=true)"
            )
        else:
            con.execute(
                f"CREATE TABLE {table} AS SELECT * FROM read_csv('{path}', header=true, all_varchar=true)"
            )
    for sql_file in SQL_FILES:
        con.execute((ROOT / "sql" / sql_file).read_text())
    return con


def export(con: duckdb.DuckDBPyConnection, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, query in EXTRACTS.items():
        df = con.execute(query).df()
        df.to_csv(out_dir / f"{name}.csv", index=False)
        counts[name] = len(df)
    return counts


def summary(con: duckdb.DuckDBPyConnection) -> dict:
    q = lambda sql: con.execute(sql).fetchone()
    poly06, poly19 = q("""SELECT
        MAX(attendances_validated) FILTER (WHERE year = 2006),
        MAX(attendances_validated) FILTER (WHERE year = 2019)
        FROM fct_outpatient_annual WHERE care_setting = 'Polyclinics'""")
    chronic = dict(con.execute("SELECT year, chronic_pct_of_diagnoses FROM fct_chronic_share").fetchall())
    alerts = con.execute("""SELECT disease_short, alert_status, COUNT(*) FROM fct_weekly_disease
        WHERE alert_status IN ('Above expected', 'Below expected')
        GROUP BY ALL ORDER BY ALL""").fetchall()
    return {
        "polyclinic_attendances_2006": int(poly06),
        "polyclinic_attendances_2019": int(poly19),
        "polyclinic_growth_2006_2019_pct": round(100 * (poly19 / poly06 - 1), 1),
        "polyclinic_cagr_2006_2019_pct": round(100 * ((poly19 / poly06) ** (1 / 13) - 1), 2),
        "chronic_pct_of_diagnoses": {str(k): v for k, v in sorted(chronic.items())},
        "weekly_rows": q("SELECT COUNT(*) FROM fct_weekly_disease")[0],
        "weeks_with_baseline": q("SELECT COUNT(*) FROM fct_weekly_disease WHERE alert_status <> 'No baseline'")[0],
        "alert_counts": [{"disease": d, "status": s, "weeks": n} for d, s, n in alerts],
        "dq_issues": q("SELECT COUNT(*) FROM fct_dq_issues")[0],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "processed" / "sg_healthcare.duckdb")
    ap.add_argument("--out", type=Path, default=ROOT / "tableau" / "extracts")
    args = ap.parse_args()
    con = build(args.raw, args.db)
    counts = export(con, args.out)
    stats = summary(con)
    stats["extract_rows"] = counts
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
