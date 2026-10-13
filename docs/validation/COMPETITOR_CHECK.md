# Competitor and integrator check

Desk research only shows what vendors publish. Before the decision gate, book
a demo with each vendor below (as a prospective customer, honestly described
as researching options) and fill in the table. Ask them to *show* each item
in the product, not describe it.

## Inventory and POS vendors

| Question | Uzapoint | Veira | One of: iOSoft / ArmPOS / Absolute |
|---|---|---|---|
| Monthly price for 2 branches, 5 users |  |  |  |
| Setup or training fee |  |  |  |
| Stock per branch, live |  |  |  |
| Transfer between branches with an "in transit" state |  |  |  |
| Purchase order needs approval before sending |  |  |  |
| Approval limit by role |  |  |  |
| Receive part of a PO, rest stays outstanding |  |  |  |
| Blocks receiving more than ordered |  |  |  |
| Stock adjustment needs a reason and records who did it |  |  |  |
| Audit log the owner can read |  |  |  |
| Stock valuation method (average, FIFO) |  |  |  |
| Customer credit limits and ageing (30/60/90) |  |  |  |
| Match an M-Pesa payment to a specific invoice |  |  |  |
| eTIMS: OSCU or VSCU, or through an integrator |  |  |  |
| Works with poor internet |  |  |  |
| Export data (CSV/Excel) |  |  |  |

Mark each cell: **Yes (shown)**, **Yes (told, not shown)**, **No**, or
**Unclear**. Only "Yes (shown)" counts as yes.

## eTIMS integrators (for option A2)

Contact two KRA-verified third-party integrators (KRA publishes the list on
kra.go.ke under eTIMS). Ask:

1. Do you offer an API another system can use to issue eTIMS invoices and credit notes?
2. Pricing: per invoice, per month, setup fee?
3. Is there a sandbox we can test against?
4. What happens when KRA or your service is unavailable? Can invoices queue?
5. How are buyer PINs, item classification codes and tax types passed?
6. Contract terms: minimum period, notice, data ownership.

## What would change our plan

- Two or more vendors show working transfers in transit, PO approval and
  partial receiving at a price below KSh 6,000/month: our gap is not real for
  stock and purchasing. Look for a different wedge, or stop.
- No vendor shows them: the gap holds, subject to interviews (A4).
- An integrator offers an affordable API with a sandbox: option A2 becomes the
  default for the sales module.
