"""Generate a packaged Tableau workbook (.twbx) from the CSV extracts.

Usage:
    python scripts/build_workbook.py   # writes tableau/sg_healthcare_utilisation.twbx

The workbook has three dashboards (Demand, Chronic Disease, Weekly Alerts) built on
four text-file data sources packaged inside the .twbx, so it opens in Tableau Public
without any extra setup.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import uuid

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXTRACTS = ROOT / "tableau" / "extracts"
OUT = ROOT / "tableau" / "sg_healthcare_utilisation.twbx"
TWB_NAME = "sg_healthcare_utilisation.twb"

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------
# column -> (datatype, role, type)
DIM_S = ("string", "dimension", "nominal")
DIM_I = ("integer", "dimension", "ordinal")
MEA_I = ("integer", "measure", "quantitative")
MEA_R = ("real", "measure", "quantitative")
DATE = ("date", "dimension", "ordinal")

SOURCES = {
    "outpatient_annual": {
        "id": "federated.outpatient",
        "caption": "Outpatient attendances",
        "cols": {
            "year": DIM_I, "care_setting": DIM_S, "care_setting_short": DIM_S, "care_level": DIM_S,
            "sort_order": DIM_I, "attendances_reported": MEA_I, "attendances_validated": MEA_R,
            "yoy_change_pct": MEA_R, "index_2006_eq_100": MEA_R, "neighbour_ratio": MEA_R,
            "dq_status": DIM_S, "year_total_validated": MEA_R, "year_polyclinic_share": MEA_R,
        },
        "calcs": {},
    },
    "polyclinic_conditions": {
        "id": "federated.conditions",
        "caption": "Polyclinic conditions",
        "cols": {
            "year": DIM_I, "condition": DIM_S, "condition_short": DIM_S, "condition_type": DIM_S,
            "sort_order": DIM_I, "pct_of_diagnoses": MEA_R, "pp_change_yoy": MEA_R,
            "rank_in_year": DIM_I, "year_chronic_pct_of_diagnoses": MEA_R,
        },
        "calcs": {},
    },
    "weekly_alerts": {
        "id": "federated.weekly",
        "caption": "Weekly polyclinic attendances",
        "cols": {
            "week_start": DATE, "week_end": DATE, "epi_year": DIM_I, "epi_week_num": DIM_I,
            "epi_week_label": DIM_S, "disease": DIM_S, "disease_short": DIM_S, "sort_order": DIM_I,
            "avg_daily_attendances": MEA_I, "baseline_n": MEA_R, "baseline_mean": MEA_R,
            "baseline_sd": MEA_R, "upper_limit": MEA_R, "lower_limit": MEA_R, "ratio_to_expected": MEA_R,
            "alert_status": DIM_S, "dq_note": DIM_S,
        },
        "calcs": {},
    },
    "dq_issues": {
        "id": "federated.dq",
        "caption": "Data-quality issues",
        "cols": {
            "dataset": DIM_S, "record": DIM_S, "reported_value": MEA_I,
            "issue": DIM_S, "rule": DIM_S, "handling": DIM_S,
        },
        "calcs": {},
    },
}

PALETTES = {
    # (source, field instance) -> {member: colour}
    ("outpatient_annual", "care_setting_short"): {
        "Polyclinics": "#1F6F8B", "SOCs": "#7FA7B5", "A&E": "#C8553D", "Dental": "#A3A3A3"},
    ("polyclinic_conditions", "condition_short"): {
        "Hyperlipidaemia": "#1F6F8B", "Hypertension": "#4C9AB3", "Diabetes": "#99C4D3", "Acute URTI": "#C8553D"},
    ("polyclinic_conditions", "condition_type"): {"Chronic": "#1F6F8B", "Acute": "#C8553D"},
    ("weekly_alerts", "alert_status"): {
        "Above expected": "#C8553D", "Below expected": "#3A7CA5",
        "Within expected": "#D9D9D9", "No baseline": "#F4F4F4"},
}


def simple_id(name: str) -> str:
    """Stable simple-id element for a sheet, dashboard or window."""
    return f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_URL, 'sg-health/' + name)).upper()}}}' />"


def q(s: str) -> str:
    return quoteattr(s)


def datasource_xml(key: str, spec: dict) -> str:
    fname = f"{key}.csv"
    rel_cols = "".join(
        f"<column datatype={q(dt)} name={q(c)} ordinal='{i}' />"
        for i, (c, (dt, _, _)) in enumerate(spec["cols"].items())
    )
    ds_cols = "".join(
        f"<column caption={q(c.replace('_', ' ').title())} datatype={q(dt)} name={q(f'[{c}]')} "
        f"role={q(role)} type={q(typ)} />"
        for c, (dt, role, typ) in spec["cols"].items()
    )
    calc_cols = "".join(
        f"<column caption={q(cap)} datatype='real' name={q(f'[{name}]')} role='measure' type='quantitative'>"
        f"<calculation class='tableau' formula={q(formula)} /></column>"
        for name, (cap, formula) in spec["calcs"].items()
    )
    styles = ""
    for (src, field), cmap in PALETTES.items():
        if src != key:
            continue
        maps = "".join(f"<map to={q(col)}><bucket>{escape(chr(34) + m + chr(34))}</bucket></map>"
                       for m, col in cmap.items())
        styles += (f"<style-rule element='mark'><encoding attr='color' field={q(f'[none:{field}:nk]')} "
                   f"type='palette'>{maps}</encoding></style-rule>")
    style_xml = f"<style>{styles}</style>"
    return (
        f"<datasource caption={q(spec['caption'])} inline='true' name={q(spec['id'])} version='18.1'>"
        f"<connection class='federated'><named-connections>"
        f"<named-connection caption={q(key)} name={q('textscan.' + key)}>"
        f"<connection class='textscan' directory='Data/extracts' filename={q(fname)} password='' server='' />"
        f"</named-connection></named-connections>"
        f"<relation connection={q('textscan.' + key)} name={q(fname)} table={q(f'[{key}#csv]')} type='table'>"
        f"<columns character-set='UTF-8' header='yes' locale='en_GB' separator=','>{rel_cols}</columns>"
        f"</relation></connection>"
        f"<aliases enabled='yes' />{ds_cols}{calc_cols}"
        f"<layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' "
        f"measure-percentage='0.4' show-structure='true' />{style_xml}"
        f"<semantic-values><semantic-value key='[Country].[Name]' value='&quot;Singapore&quot;' /></semantic-values>"
        f"</datasource>"
    )


# ---------------------------------------------------------------------------
# Field references
# ---------------------------------------------------------------------------
class F:
    """A column instance used on a shelf."""

    def __init__(self, src: str, col: str, agg: str = "None", kind: str = "nk", calc: bool = False):
        self.src, self.col, self.agg, self.kind, self.calc = src, col, agg, kind, calc

    @property
    def prefix(self) -> str:
        return {"None": "none", "Sum": "sum", "Min": "min", "Avg": "avg", "Cnt": "cnt", "User": "usr", "Day-Trunc": "tdy"}[self.agg]

    @property
    def inst(self) -> str:
        return f"[{self.prefix}:{self.col}:{self.kind}]"

    @property
    def ref(self) -> str:
        return f"[{SOURCES[self.src]['id']}].{self.inst}"

    @property
    def type(self) -> str:
        return {"nk": "nominal", "ok": "ordinal", "qk": "quantitative"}[self.kind]

    def instance_xml(self) -> str:
        return (f"<column-instance column={q(f'[{self.col}]')} derivation={q(self.agg)} "
                f"name={q(self.inst)} pivot='key' type={q(self.type)} />")

    def column_xml(self) -> str:
        spec = SOURCES[self.src]
        if self.calc:
            cap, formula = spec["calcs"][self.col]
            return (f"<column caption={q(cap)} datatype='real' name={q(f'[{self.col}]')} role='measure' "
                    f"type='quantitative'><calculation class='tableau' formula={q(formula)} /></column>")
        dt, role, typ = spec["cols"][self.col]
        return (f"<column caption={q(self.col.replace('_', ' ').title())} datatype={q(dt)} "
                f"name={q(f'[{self.col}]')} role={q(role)} type={q(typ)} />")


def dim(src, col, kind="nk"):
    return F(src, col, "None", kind)


def mea(src, col, agg="Sum"):
    return F(src, col, agg, "qk")


def member_filter(f: F, members: list[str], numeric: bool = False) -> str:
    def m(v):
        return escape(v if numeric else f'"{v}"', {"'": "&apos;"})
    inner = "".join(f"<groupfilter function='member' level={q(f.inst)} member='{m(v)}' />" for v in members)
    if len(members) > 1:
        inner = f"<groupfilter function='union' user:op='manual'>{inner}</groupfilter>"
    else:
        inner = inner.replace("<groupfilter function='member'", "<groupfilter function='member' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate'", 1)
    return f"<filter class='categorical' column={q(f.ref)}>{inner}</filter>"


def worksheet(name: str, src: str, rows: list[F], cols: list[F], mark: str,
              color: F | None = None, text: F | None = None, size: F | None = None,
              filters: list[tuple[F, list[str], bool]] = (), extra: list[F] = (),
              title: str | None = None) -> str:
    fields = {f.col: f for f in [*rows, *cols, *(x for x in (color, text, size) if x), *(x[0] for x in filters), *extra]}
    instances = {f.inst: f for f in [*rows, *cols, *(x for x in (color, text, size) if x), *(x[0] for x in filters), *extra]}
    # Columns used inside calculated fields must also be declared on the sheet.
    import re
    for f in list(fields.values()):
        if f.calc:
            for base in re.findall(r"\[([^\]]+)\]", SOURCES[src]["calcs"][f.col][1]):
                fields.setdefault(base, F(src, base))
    deps = "".join(f.column_xml() for f in fields.values()) + "".join(f.instance_xml() for f in instances.values())
    sid = SOURCES[src]["id"]
    enc = ""
    if color:
        enc += f"<color column={q(color.ref)} />"
    if text:
        enc += f"<text column={q(text.ref)} />"
    if size:
        enc += f"<size column={q(size.ref)} />"
    filt = "".join(member_filter(f, m, n) for f, m, n in filters)
    if filters:
        filt += "<slices>" + "".join(f"<column>{escape(f.ref)}</column>" for f, _, _ in filters) + "</slices>"
    shelf = lambda fs: " / ".join(f.ref for f in fs) if len(fs) > 1 else (fs[0].ref if fs else "")
    title_xml = (f"<layout-options><title><formatted-text><run bold='true' fontsize='12'>{escape(title)}</run>"
                 f"</formatted-text></title></layout-options>") if title else ""
    return (
        f"<worksheet name={q(name)}>{title_xml}<table><view>"
        f"<datasources><datasource caption={q(SOURCES[src]['caption'])} name={q(sid)} /></datasources>"
        f"<datasource-dependencies datasource={q(sid)}>{deps}</datasource-dependencies>"
        f"{filt}<aggregation value='true' /></view><style />"
        f"<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
        f"<view><breakdown value='auto' /></view><mark class={q(mark)} />"
        f"<encodings>{enc}</encodings></pane></panes>"
        f"<rows>{escape(shelf(rows))}</rows><cols>{escape(shelf(cols))}</cols>"
        f"</table>{simple_id('ws/' + name)}</worksheet>"
    )


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
O, C, W, D = "outpatient_annual", "polyclinic_conditions", "weekly_alerts", "dq_issues"

SHEETS = [
    worksheet("Attendances by Care Setting", O,
              rows=[mea(O, "attendances_validated")], cols=[dim(O, "year", "ok")], mark="Line",
              color=dim(O, "care_setting_short"),
              title="Annual attendances by care setting (validated; gaps = suspected entry errors)"),
    worksheet("Growth Index", O,
              rows=[mea(O, "index_2006_eq_100")], cols=[dim(O, "year", "ok")], mark="Line",
              color=dim(O, "care_setting_short"),
              title="Growth index (2006 = 100): polyclinics grew fastest, +77.5% by 2019"),
    worksheet("Total Attendances", O,
              rows=[mea(O, "year_total_validated", "Min")], cols=[dim(O, "year", "ok")], mark="Bar",
              title="Total public outpatient attendances (2014 and 2017 not totalled)"),
    worksheet("2020 Change by Setting", O,
              rows=[dim(O, "care_setting_short")], cols=[mea(O, "yoy_change_pct")], mark="Bar",
              color=dim(O, "care_setting_short"),
              filters=[(dim(O, "year", "ok"), ["2020"], True)],
              title="2020 change vs 2019 (%)"),
    worksheet("Share of Diagnoses", C,
              rows=[mea(C, "pct_of_diagnoses")], cols=[dim(C, "year", "ok")], mark="Line",
              color=dim(C, "condition_short"),
              title="% of all polyclinic diagnoses by condition"),
    worksheet("Chronic vs Acute", C,
              rows=[mea(C, "pct_of_diagnoses")], cols=[dim(C, "year", "ok")], mark="Area",
              color=dim(C, "condition_type"),
              title="Chronic conditions (hyperlipidaemia, hypertension, diabetes) vs acute URTI"),
    worksheet("Weekly Ratio to Expected", W,
              rows=[dim(W, "disease_short"), mea(W, "ratio_to_expected", "Avg")],
              cols=[F(W, "week_start", "Day-Trunc", "qk")], mark="Circle",
              color=dim(W, "alert_status"),
              title="Weekly attendances as a ratio of expected (1.0 = baseline mean)"),
    worksheet("Alert Calendar", W,
              rows=[dim(W, "disease_short"), dim(W, "epi_year", "ok")], cols=[dim(W, "epi_week_num", "ok")],
              mark="Square", color=dim(W, "alert_status"),
              title="Alert calendar: weeks above (red) or below (blue) the expected range"),
    worksheet("Data Quality Log", D,
              rows=[dim(D, "record"), dim(D, "issue"), dim(D, "handling")], cols=[], mark="Text",
              text=mea(D, "reported_value"),
              title="Data-quality issues found and how they are handled"),
]

SHEET_NAMES = [s.split("name=", 1)[1].split(">", 1)[0].strip("\"'") for s in SHEETS]


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------
_zid = iter(range(1, 10_000))


def text_zone(x, y, w, h, runs: list[tuple[str, int, bool]]) -> str:
    body = "".join(
        f"<run bold={q('true' if b else 'false')} fontsize='{s}'>{escape(t)}</run><run>Æ&#10;</run>"
        for t, s, b in runs
    )
    return (f"<zone h='{h}' id='{next(_zid)}' type-v2='text' w='{w}' x='{x}' y='{y}'>"
            f"<formatted-text>{body}</formatted-text></zone>")


def sheet_zone(name, x, y, w, h) -> str:
    return f"<zone h='{h}' id='{next(_zid)}' name={q(name)} w='{w}' x='{x}' y='{y}' />"


def dashboard(name: str, zones: list[str]) -> str:
    sources = "".join(
        f"<datasource caption={q(v['caption'])} name={q(v['id'])} />" for v in SOURCES.values()
    )
    return (
        f"<dashboard name={q(name)}><style />"
        f"<size maxheight='900' maxwidth='1300' minheight='900' minwidth='1300' />"
        f"<datasources>{sources}</datasources>"
        f"<zones><zone h='100000' id='{next(_zid)}' type-v2='layout-basic' w='100000' x='0' y='0'>"
        f"{''.join(zones)}</zone></zones>"
        f"<devicelayouts><devicelayout name='Phone'>"
        f"<size maxheight='700' minheight='700' sizing-mode='vscroll' />"
        f"<zones><zone h='100000' id='{next(_zid)}' type-v2='layout-basic' w='100000' x='0' y='0' />"
        f"</zones></devicelayout></devicelayouts>{simple_id('db/' + name)}</dashboard>"
    )


SOURCE_NOTE = "Source: Ministry of Health via data.gov.sg (Singapore Open Data Licence). Descriptive statistics only."

DASHBOARDS = {
    "1 Demand": [
        text_zone(0, 0, 100000, 9000, [
            ("Singapore public outpatient demand, 2006–2021", 18, True),
            ("Polyclinic attendances 6.69M in 2019 (+77.5% since 2006)  ·  Polyclinic share 47.4% of public outpatient attendances  ·  2 suspected entry errors excluded", 11, False)]),
        sheet_zone("Attendances by Care Setting", 0, 9000, 60000, 45000),
        sheet_zone("Growth Index", 60000, 9000, 40000, 45000),
        sheet_zone("Total Attendances", 0, 54000, 60000, 41000),
        sheet_zone("2020 Change by Setting", 60000, 54000, 40000, 41000),
        text_zone(0, 95000, 100000, 5000, [(SOURCE_NOTE, 9, False)]),
    ],
    "2 Chronic Disease": [
        text_zone(0, 0, 100000, 9000, [
            ("Chronic disease in Singapore's polyclinics, 2006–2025", 18, True),
            ("Hyperlipidaemia, hypertension and diabetes = 36–42% of all diagnoses each year (36.1% in 2025)  ·  URTI fell from 8.6% (2019) to 3.6% (2021)", 11, False)]),
        sheet_zone("Share of Diagnoses", 0, 9000, 100000, 46000),
        sheet_zone("Chronic vs Acute", 0, 55000, 100000, 40000),
        text_zone(0, 95000, 100000, 5000, [
            ("Shares are of all diagnoses (several per visit possible) and exclude preventive-care visits. " + SOURCE_NOTE, 9, False)]),
    ],
    "3 Weekly Alerts": [
        text_zone(0, 0, 100000, 9000, [
            ("Weekly polyclinic attendances vs expected range, 2012–2022", 18, True),
            ("Expected range = mean ± 2 SD of the same weeks in the previous 5 years. 2020: 40–46 of 53 weeks below expected for every acute disease.", 11, False)]),
        sheet_zone("Weekly Ratio to Expected", 0, 9000, 58000, 86000),
        sheet_zone("Alert Calendar", 58000, 9000, 42000, 66000),
        sheet_zone("Data Quality Log", 58000, 75000, 42000, 20000),
        text_zone(0, 95000, 100000, 5000, [
            ("Screening flags for review, not proof of an outbreak. The rule does not adjust for population growth. " + SOURCE_NOTE, 9, False)]),
    ],
}


def windows_xml() -> str:
    ws = "".join(
        f"<window class='worksheet' name={q(n)}><cards><edge name='left'><strip size='160'>"
        f"<card type='pages' /><card type='filters' /><card type='marks' /></strip></edge>"
        f"<edge name='top'><strip size='2147483647'><card type='columns' /></strip>"
        f"<strip size='2147483647'><card type='rows' /></strip><strip size='31'><card type='title' /></strip>"
        f"</edge></cards>{simple_id('win/' + n)}</window>"
        for n in SHEET_NAMES
    )
    ds = "".join(
        f"<window class='dashboard' maximized='true' name={q(n)}><viewpoints /><active id='-1' />"
        f"<device-preview visible='false' />{simple_id('win/' + n)}</window>"
        for n in DASHBOARDS)
    return f"<windows source-height='30'>{ds}{ws}</windows>"


def workbook_xml() -> str:
    return (
        "<?xml version='1.0' encoding='utf-8' ?>\n"
        "<workbook original-version='18.1' source-build='2024.2.0 (20242.24.0807.0327)' source-platform='win' "
        "version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>"
        "<document-format-change-manifest><SheetIdentifierTracking /><WindowsPersistSimpleIdentifiers />"
        "</document-format-change-manifest>"
        "<preferences><preference name='ui.encoding.shelf.height' value='24' />"
        "<preference name='ui.shelf.height' value='26' /></preferences>"
        f"<datasources>{''.join(datasource_xml(k, v) for k, v in SOURCES.items())}</datasources>"
        f"<worksheets>{''.join(SHEETS)}</worksheets>"
        f"<dashboards>{''.join(dashboard(n, z) for n, z in DASHBOARDS.items())}</dashboards>"
        f"{windows_xml()}</workbook>\n"
    )


def main() -> None:
    xml = workbook_xml()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(TWB_NAME, xml)
        for key in SOURCES:
            z.write(EXTRACTS / f"{key}.csv", f"Data/extracts/{key}.csv")
    (ROOT / "tableau" / TWB_NAME).write_text(xml)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(SHEETS)} sheets, {len(DASHBOARDS)} dashboards)")


if __name__ == "__main__":
    main()
