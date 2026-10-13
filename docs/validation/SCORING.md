# Scoring the interviews and making the decision

After every five interviews, tally the scorecards from `tracker.csv`.

| Assumption | Pass threshold (of 10) | Count so far | Result |
|---|---|---|---|
| A1 Stock pain is top-3, unprompted | ≥ 6 |  |  |
| A2 Multi-branch transfer/visibility problem | ≥ 4 of the 6+ multi-branch |  |  |
| A3 Concrete recent purchasing loss | ≥ 5 |  |  |
| A4 Workaround outside current system | ≥ 5 |  |  |
| A5 Would use a separate stock tool next to their invoicing | ≥ 5 |  |  |
| A6 Paid pilot at ≥ KSh 3,000/month | ≥ 3 |  |  |
| A7 Device available at receiving/dispatch | ≥ 6 |  |  |

Rules:

- Count only answers backed by a specific recent example. "Yes, that's a
  problem" without an example counts as a fail.
- Don't change thresholds after seeing results. If a threshold was wrong,
  write down why in VALIDATION.md §7 and apply the new one to the next
  round only.
- Combine with COMPETITOR_CHECK.md before deciding.

Then pick the outcome from VALIDATION.md §5 and record it, with the counts, in
VALIDATION.md §7.
