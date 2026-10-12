# Demo Script (15 minutes)

A fixed walk-through for showing the project to a reviewer or interviewer. Every step has a
command, what appears, and what to say. **The numbers are identical on every run**: the data
is generated with a fixed seed and fixed dates, and the pipeline rebuilds deterministically.
Nothing in this demo calls a paid API.

## Before the demo (5 minutes, once)

```powershell
cd "<project folder>"
.venv\Scripts\activate
python scripts/check_environment.py         # database reachable, AI mode shown
python scripts/run_pipeline.py              # fresh run before the demo (~2.5 min)
```

Open in advance: `README.md` (architecture diagram), the Power BI report if it has been
built, and a terminal with a large font.

---

## 1. The problem (1 min), no commands

> "AutoSphere is a fictional car dealer and service company with branches across Georgia.
> Management wants one trusted view of sales, service and customer satisfaction. The raw
> data is messy, and customer feedback is free text in Georgian and English. I built the
> whole chain: data, cleaning, warehouse, KPIs, AI, Power BI and automated reporting."

Show the **architecture diagram** in `README.md`.

## 2. Messy source data (1 min)

```powershell
python scripts/inspect_database.py --query "SELECT reason, count(*) FROM audit.rejected_rows WHERE run_id = (SELECT max(run_id) FROM audit.rejected_rows) GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
```
**Expected:** reasons such as exact duplicates, orphan references, negative quantities, future dates.

> "The generator injects 38 kinds of real-world defects on purpose. Every bad row is
> quarantined with a reason, never silently dropped, and a test proves all 38 types are caught."

## 3. One command proves the whole platform (3 min)

```powershell
python scripts/validate_end_to_end.py --skip-pipeline
```
**Expected:** 16 lines of `PASS`, ending in `16/16 checks passed`.

Point at three lines:
- **`113,531 raw = 110,485 staging + 3,046 quarantined`**: "not a single row is lost".
- **`28,441,790.18 GEL in all three`**: "warehouse, SQL KPIs and the Power BI layer show the same revenue".
- **`0 critical failures`**: "340 quality checks ran; a critical one would roll the load back".

(Without `--skip-pipeline` it also runs the pipeline first: ~3 minutes.)

## 4. The warehouse and a business question (2 min)

```powershell
python scripts/run_analytics.py 03
```
**Expected:** Kutaisi `Declining`, −16.37% YTD, orders −27.85%.

> "This is a star schema: sales lines in the middle, with branches, products, customers and
> dates around it. Growth compares year-to-date with the same window last year. The data ends
> in September, so a naive full-year comparison would show the whole company at −18.5%, but
> it is actually +15.6%. Kutaisi's decline comes from fewer customers, not smaller baskets."

Optional: `python scripts/demo_scd2.py` shows SCD Type 2 history for one customer (rolled back).

## 5. AI on customer feedback (3 min)

```powershell
python scripts/classify_feedback.py "სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი." --provider local
```
**Expected:** `language=ka  sentiment=negative  topic=waiting_time` (free local classifier).

```powershell
python scripts/inspect_database.py --query "SELECT branch_name, topic, year_quarter, negative_count, ratio_to_baseline FROM analytics.v_feedback_anomalies WHERE is_anomaly AND year = 2026 ORDER BY ratio_to_baseline DESC LIMIT 5"
python scripts/run_analytics.py 10
```
**Expected:** a Batumi `waiting_time` anomaly; Batumi maintenance turnaround 2.8 h → 7.1 h, `INVESTIGATE`.

> "10,352 comments were classified by Gemini, validated against a fixed label set and cached,
> so they are never paid for twice. AI shows Batumi's waiting-time complaints doubled, and
> the operational data shows Batumi's turnaround went from 2.8 to 7.1 hours in the same
> quarters. Two independent sources, one story. On a hand-written test set with new phrasing,
> Gemini scores 100% on sentiment; a keyword approach scores 27.5%."

## 6. Automated management report (2 min)

```powershell
python scripts/generate_report.py
start reports\management\latest.html
```
**Expected:** 5 HIGH alerts (Kutaisi, Batumi turnaround, three feedback anomalies), KPI
cards, branch table, AI summary.

> "This runs every morning from Task Scheduler, cron or GitHub Actions. If a refresh fails,
> the load rolls back and the report shows a red banner naming the last good run: old numbers
> are clearly labelled, wrong numbers never appear. The job never calls the paid AI by default."

## 7. Power BI (2 min)

If the report has been built: show page 1 (Executive Overview) and page 7 (Customer Feedback).
Otherwise show `powerbi/dashboard-spec.md` and `powerbi/dax-measures.md`.

```powershell
python scripts/powerbi_reference.py
```
> "Power BI reads only a dedicated `bi` layer that contains no customer contact data. These
> are the numbers every card must show, and a test checks that every column used in DAX
> exists in the database."

## 8. Quality and tests (1 min)

```powershell
pytest -m "not db" -q
```
**Expected:** `166 passed` in about 15 seconds. The full suite (`pytest`) has 236 tests,
including database tests. CI runs the offline suite on every push.

> "Every KPI is computed three independent ways and compared. The most important rule, that a
> failed load never replaces good data, has its own integration test."

---

## If something goes wrong during the demo

| Problem | What to do / say |
|---------|------------------|
| Database is slow to respond at first (hosted free tier) | Run `python scripts/check_environment.py` once and wait ~30 s |
| No internet | `pytest -m "not db"` and `python scripts/classify_feedback.py` work offline; show `reports/e2e_validation.md` from the last run |
| Question about AI cost | "One full Gemini classification of 10k comments was ~0.9M tokens. After that only new comments are sent, and the scheduled job uses the free local mode." |
| "Is this real data?" | "No. It is fully synthetic with a fixed seed, so every number in this demo is reproducible." |
