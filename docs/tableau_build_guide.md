# Tableau build guide

This guide walks through building the three-page dashboard in **Tableau Public (desktop)** from the CSVs in `tableau/extracts/`. Allow 2–3 hours. Field names below are as Tableau shows them after import (it turns `attendances_validated` into **Attendances Validated**).

Run `python scripts/build_model.py` first if you changed anything in `data/raw/` or `sql/`.

---

## 0. Connect the data

1. Open Tableau Public → **Connect → Text file** → `tableau/extracts/outpatient_annual.csv`.
2. **Data → New Data Source** for each of `polyclinic_conditions.csv`, `weekly_alerts.csv` and `dq_issues.csv`. Keep them as four separate data sources. No joins or relationships are needed.
3. In each source, check the types:
   - `Year` and `Epi Year`: right-click → **Convert to Discrete**, and make sure they are numbers, not dates.
   - `Week Start`: **Date**.
   - `Sort Order`, `Rank In Year`, `Epi Week Num`, `Baseline N`: **Convert to Dimension**.
4. Sort the label fields: right-click `Care Setting Short` → **Default Properties → Sort → Field: Sort Order, Minimum**. Do the same for `Condition Short` and `Disease Short`.

### Colours (use on every page)

| Item | Hex |
|---|---|
| Polyclinics / primary care | `#1F6F8B` |
| SOCs | `#7FA7B5` |
| A&E | `#C8553D` |
| Dental | `#A3A3A3` |
| Chronic conditions | `#1F6F8B`, `#4C9AB3`, `#99C4D3` |
| Acute URTI | `#C8553D` |
| Above expected | `#C8553D` |
| Below expected | `#3A7CA5` |
| Within expected / expected range | `#D9D9D9` |

---

## Page 1: Public outpatient demand (`outpatient_annual`)

### Calculated fields

```
// Suspected Error Point
IF [Dq Status] = "Suspected entry error" THEN [Attendances Reported] END
```
```
// Year Total (M)
MIN([Year Total Validated]) / 1000000
```
The year total repeats on every care-setting row, so always aggregate it with MIN, not SUM.
```
// Polyclinic Share
MIN([Year Polyclinic Share])
```
Format it as a percentage with 1 decimal place.

### Sheets

**1a. KPI cards** (three small sheets, mark type Text, large font)
- *Polyclinic attendances, 2019*: filter `Year` = 2019 and `Care Setting Short` = Polyclinics, show SUM(Attendances Validated). Expected value: **6,691,295**.
- *Growth since 2006 (pre-COVID)*: filter Polyclinics and `Year` = 2019, show SUM(Index 2006 Eq 100) − 100 → **+77.5%**. Add a caption: "Polyclinic attendances, 2006 to 2019".
- *Polyclinic share of public outpatient attendances, 2019*: filter `Year` = 2019, show [Polyclinic Share] → **47.4%**.

**1b. Attendances by care setting (line chart)**
- Columns: `Year`. Rows: SUM(Attendances Validated). Colour: `Care Setting Short`.
- Drag SUM(Suspected Error Point) to Rows and make it a **dual axis**, then **Synchronise Axis**. Set its mark type to Shape (✕) in red, size small.
- Right-click the line axis → **Format → Pane → Special Values** and pick the option that breaks the line (hide the marks and break the line), so validated nulls show as gaps.
- Tooltip: `Care Setting`, `Year`, Attendances Reported, `Dq Status`, Yoy Change Pct.
- Title: "Polyclinics grew fastest; two published values look like entry errors (✕)".

**1c. Total public outpatient attendances (bar chart)**
- Columns: `Year`. Rows: [Year Total (M)].
- 2014 and 2017 will be empty. Add an annotation: "Not totalled: one setting failed validation".

**1d. 2020 COVID-19 drop (horizontal bar chart)**
- Filter `Year` = 2020. Rows: `Care Setting Short`. Columns: SUM(Yoy Change Pct).
- Expected values: Dental −34.5%, A&E −16.5%, SOCs −15.3%, Polyclinics −10.4%.

**Dashboard "1 Demand"**: size **Automatic** or 1200 × 900. Put the KPI cards on top, 1b on the left (wide), and 1c and 1d stacked on the right. Use a single text subtitle: "Source: MOH via data.gov.sg. Validated values exclude 2 suspected entry errors."

---

## Page 2: Chronic disease in polyclinics (`polyclinic_conditions`)

### Calculated fields
```
// Chronic Share
MIN([Year Chronic Pct Of Diagnoses])
```
```
// Latest Year Flag
[Year] = {FIXED : MAX([Year])}
```

### Sheets

**2a. KPI cards**
- *Chronic share of diagnoses, latest year*: filter [Latest Year Flag] = True, show [Chronic Share] → **36.1% (2025)**.
- *Peak*: **41.8% (2008)**. Make it with a table calculation, or type it as text from `reports/summary.json`.

**2b. Share of diagnoses by condition (line chart)**
- Columns: `Year`. Rows: SUM(Pct Of Diagnoses). Colour: `Condition Short`. Label: the line ends.
- Add annotations at 2020: "URTI fell from 8.6% (2019) to 3.6% (2021) during COVID-19 measures".

**2c. Chronic vs acute (area chart)**
- Columns: `Year`. Rows: SUM(Pct Of Diagnoses). Colour: `Condition Type`. Mark: Area.
- Caption: "Shares are of all diagnoses, which can include several per visit."

**2d. Rank heat table**
- Rows: `Condition Short`. Columns: `Year`. Text and Colour: MIN(Rank In Year), with a reversed sequential palette.

**Dashboard "2 Chronic"**: KPI cards on top, 2b large, then 2c and 2d below.

---

## Page 3: Weekly alerts (`weekly_alerts` and `dq_issues`)

### Parameter and calculated fields

1. **Create Parameter** `p Disease`: String, List, **Add values from → Disease Short**, current value "Acute URTI". Right-click → **Show Parameter**.
```
// Selected Disease
[Disease Short] = [p Disease]
```
Put this on Filters for 3a and 3b, set to True.
```
// Band Height
[Upper Limit] - [Lower Limit]
```
```
// Alert Point
IF [Alert Status] = "Above expected" OR [Alert Status] = "Below expected"
THEN [Avg Daily Attendances] END
```
```
// Alert Week
IF [Alert Status] = "Above expected" THEN 1
ELSEIF [Alert Status] = "Below expected" THEN -1
ELSE 0 END
```

### Sheets

**3a. Weekly attendances vs expected range** (the key chart)
1. Columns: `Week Start` (continuous, exact date). Rows: **Measure Values**. Keep only SUM(Lower Limit) and SUM(Band Height) on the Measure Values card.
2. Mark type: **Area**. Make sure **Analysis → Stack Marks → On**. Colour by Measure Names: Lower Limit **white at 0% opacity**, Band Height `#D9D9D9`. This draws the expected range as a grey band.
3. Drag SUM(Avg Daily Attendances) to Rows → **Dual Axis** → **Synchronise Axis**. Mark: Line, dark grey.
4. Drag SUM(Alert Point) to Rows as a third measure. Combine it into the line axis by dropping it onto the existing line axis (Measure Values), or use a separate synced axis. Mark: Circle, coloured by `Alert Status` (red above, blue below).
5. Title: `<p Disease>`: weekly average daily attendances vs expected range.
6. Annotate the 2020 area: "Circuit breaker, Apr–Jun 2020".

**3b. Alert calendar (heat map)**
- Rows: `Epi Year`. Columns: `Epi Week Num`. Mark: Square. Colour: `Alert Status` (above red, below blue, within light grey, no baseline white).
- Filter: Selected Disease = True.

**3c. Alert weeks by disease and year (table)**
- Rows: `Disease Short`. Columns: `Epi Year`. Text: COUNT of rows filtered to `Alert Status` = Above expected. Duplicate the sheet for Below expected.
- Expected 2020 Below expected counts: Conjunctivitis 46, Acute Diarrhoea 45, Chickenpox 44, Acute URTI 40.

**3d. Data-quality log (`dq_issues` source)**
- Rows: `Dataset`, `Record`, `Reported Value`, `Issue`, `Handling`. Mark: Text. Three rows.

**Dashboard "3 Alerts"**: parameter control at the top right, 3a large, 3b below it, and 3c and 3d on the right or at the bottom. Add a text box: "Screening flags for review, not proof of an outbreak. Expected range = mean ± 2 SD of the same weeks in the previous 5 years."

---

## Publish

1. Add a navigation button (**Objects → Navigation**) on each dashboard to move between the three pages.
2. **File → Save to Tableau Public As…** → title "Singapore Public Healthcare Utilisation & Chronic Disease".
3. On Tableau Public, open the viz → **Edit details**: add the GitHub link and a one-paragraph description.
4. Take a screenshot of each dashboard into `docs/dashboard/` (`01_demand.png`, `02_chronic.png`, `03_alerts.png`) and paste the Tableau Public link into the README.

## Check before publishing

Every number on the dashboards should match `reports/summary.json` or the expected values in this guide. Check in particular:
- [ ] Polyclinic attendances 2019 = 6,691,295; growth 2006–2019 = +77.5%
- [ ] Totals for 2014 and 2017 are blank, not low
- [ ] Two red ✕ markers: SOCs 2014 and Dental 2017
- [ ] Chronic share 2025 = 36.1%; 2020 and 2021 = 40.0%
- [ ] 2020 Below expected weeks: Conjunctivitis 46, Acute Diarrhoea 45, Chickenpox 44, Acute URTI 40
- [ ] HFMD shows no alerts before 2021
