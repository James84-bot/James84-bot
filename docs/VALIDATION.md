# JMH Ops — Idea validation (before building)

Status: **in progress.** No feature beyond the Phase 1 scaffold gets built
until the experiments below have results. This document lists what we
believe, what would prove it wrong, and how we will find out cheaply.

Last updated: 13 October 2026

## 1. The bet in one paragraph

Kenyan distributors, wholesalers and hardware suppliers with 1–10 branches lose
money in three places: stock that goes missing or runs out without warning,
purchase orders that nobody approved or that suppliers deliver short, and
credit customers whose partial payments (M-Pesa, cheque, bank) are hard to
match to invoices. We believe a focused tool that keeps an honest stock ledger,
controls purchasing and keeps customer balances accurate will be worth paying
for, *even though* POS and ERP products already exist.

## 2. What the market already offers (desk research)

| Alternative | What it covers | Why a business might still look elsewhere (to be confirmed in interviews) |
|---|---|---|
| Excel / bin cards / stock book | Everything, manually | No audit trail, errors found only at monthly count |
| TallyPrime, QuickBooks | Accounting first, inventory second | Branch transfers, PO approval and per-branch stock are weak or need add-ons |
| Kenyan POS/ERP vendors (Uzapoint, Veira, iOSoft, ArmPOS, Absolute Corporate Solutions) | POS, stock, eTIMS invoicing, some M-Pesa | Mostly retail/POS-shaped; unknown how well they handle approvals, partial receiving and credit ageing |
| Odoo, ERPNext, Business Central | Full ERP, eTIMS via partners | Cost and complexity of implementation for a 5–20 person business |
| Zoho Inventory, inFlow | Good inventory | Priced in USD; no eTIMS; not built around Kenyan credit practice |

**Conclusion:** the market is crowded. "Inventory software for Kenyan SMEs" is
not a differentiator on its own. We need evidence of a specific gap.

## 3. Findings that change the plan

### 3.1 eTIMS is mandatory for invoices

Since January 2024 every Kenyan business, VAT-registered or not, must issue
tax invoices through KRA eTIMS, and KRA now cross-checks declared income and
expenses against eTIMS data. Buyer PINs are required on B2B invoices.

Consequence: **an invoicing module that does not transmit to eTIMS forces
double entry** (once in JMH Ops, once in eTIMS). A business owner would
reasonably refuse that. Options:

- **A. Integrate with eTIMS (OSCU/VSCU).** Correct long-term answer. Needs KRA
  onboarding, test credentials and certification; real effort and lead time.
- **B. Do not issue tax invoices.** JMH Ops records *sales orders / delivery
  notes* and customer balances, and the business keeps invoicing in its
  existing eTIMS-capable system. Only works if balances can be imported or
  matched without double entry.
- **C. Drop the sales/credit module** and focus on stock and purchasing,
  which eTIMS does not touch.

The Phase 3 sales module is **on hold** until interviews tell us which of
these customers will accept. Option C is the lowest-risk first release.

### 3.2 M-Pesa

Receipts will record the M-Pesa transaction code manually. No integration is
claimed. Interviews must tell us whether manual entry is acceptable or
whether automated Paybill/Till matching is the actual reason someone would
switch (in which case it moves up the roadmap and needs a real Daraja
integration).

## 4. Riskiest assumptions and how we test them

Ranked by "if wrong, the product fails" × "we know little about it".

| # | Assumption | Test | Pass if | Kill/pivot if |
|---|---|---|---|---|
| A1 | Stock discrepancies between system/books and the shelf are a top-3 problem for the owner | 10 owner interviews (script below) | ≥ 6 of 10 name stock loss, stock-outs or count variance unprompted | < 3 mention it → stock is not the wedge |
| A2 | Multi-branch businesses struggle with inter-branch transfers and stock visibility | Same interviews, filtered to 2+ branch businesses | ≥ 4 of 6 multi-branch owners describe a transfer or visibility problem | Single-branch owners dominate the segment → drop transfers from v1 |
| A3 | Purchase approval and short deliveries cost real money | Ask for the last time a supplier delivered short or an order was placed without approval, and the cost | ≥ 5 of 10 give a concrete recent example | Nobody can name one → purchasing becomes a simple "receive stock" screen |
| A4 | Existing tools (Tally, POS vendors) do not already solve A1–A3 for them | Ask what they use and walk through how they would handle a transfer and a short delivery today | Workarounds outside their system (Excel, WhatsApp, paper) for at least one of these | Their current system handles it and they are satisfied → no reason to switch |
| A5 | They will run a separate stock tool alongside their eTIMS invoicing system | Show a paper/Figma mock of option B and C; ask how they would use it next to their current invoicing | ≥ 5 of 10 say yes without "if it also did invoicing" | Most insist on one system → eTIMS integration (option A) is a prerequisite |
| A6 | They will pay a monthly fee | Price test: KSh 3,000 / 6,000 / 12,000 per month per business, asked as "which would you sign up for today" | ≥ 3 of 10 agree to a paid pilot at ≥ KSh 3,000/month | Only free use accepted → reconsider business model |
| A7 | Clerks will record movements as they happen (not at day end) | Observe one store for half a day; count movements and whether a phone/PC is at hand | Device available at receiving/dispatch points | Recording happens later from paper → design for batch entry from delivery notes |

### Who to interview

10 businesses, fictional names in notes, no customer data recorded:

- 4 hardware/building materials wholesalers (Nairobi Industrial Area, Thika, Nakuru, Kisumu)
- 3 FMCG or agro-input distributors
- 3 other inventory-based businesses (auto spares, electrical, stationery)
- At least 6 with two or more branches or a separate warehouse

Talk to the owner and, separately, the person who records stock.

### Interview script (30 minutes, no product pitch until the end)

1. Tell me about the business: branches, staff, roughly how many items you stock.
2. Walk me through what happened the last time a delivery arrived from a supplier.
3. When did you last count stock? What was the difference between the count and your records? What did you do about it?
4. When did you last run out of something a customer asked for? How did you find out?
5. Who can place an order with a supplier? Has anyone ordered something you would not have approved?
6. (Multi-branch) How do goods move between branches? How do you know they arrived?
7. How do customers on credit pay you? How do you know what each one owes?
8. What system or tools do you use for each of the above? What do you do outside it?
9. Which of these problems costs you the most money? Roughly how much a month?
10. *(Only now)* Show the mock. "If this existed tomorrow, what would you stop doing?" "What would stop you using it?"

Record answers in `docs/interviews/` using the template, one file per business.

### Prototype for testing

A clickable mock (Figma or static HTML) of three screens, built only after the
first five interviews so the questions are not led by our design:

1. Stock on hand by branch with low-stock flags.
2. Receive a delivery against a purchase order (partial delivery case).
3. A transfer from Industrial Area to Thika, in transit then received.

## 5. Decision gate

After 10 interviews we decide one of:

- **Go — stock + purchasing first (option C).** A1, A3, A4 and A5 pass.
  Resume Phase 1–2 from the scaffold in `backend/`; sales waits.
- **Go — with eTIMS.** A1–A4 pass but A5 fails. Start KRA eTIMS sandbox
  onboarding before writing any sales code; budget the time.
- **Narrow.** Only A1 passes. Build stock control only, for multi-branch businesses.
- **Stop or rethink.** A1 and A4 fail. The problem is either not painful or already solved.

Results and the decision get written at the bottom of this file.

## 6. What is already built and why it is parked

A backend scaffold (Django, PostgreSQL, roles, organisation isolation, stock
ledger with row locking, adjustments, transfers, audit log with database-level
append-only triggers) is in `backend/`. It is parked rather than extended because:

- the stock ledger and permissions are needed under every decision above
  except "stop", so the work is not wasted, but
- it has no tests yet, and must not be treated as done.

## 7. Results

_Not started._

## Sources (desk research, checked 13 October 2026)

Vendor and media sources; KRA's own notices on itax.kra.go.ke take precedence.

- Uzapoint — https://uzapoint.com/
- Veira, wholesalers — https://www.veirahq.com/solutions/inventory-management-for-wholesalers/
- iOSoft Solutions — https://www.iosoftsolutions.co.ke/best-inventory-management-software-in-kenya/
- Absolute Corporate Solutions — https://www.absolutecorporatesolutions.com/wholesale-retail-and-distribution-software-in-kenya.html
- The Retail Exec, wholesale inventory software 2026 — https://theretailexec.com/tools/best-wholesale-inventory-management-software/
- Greytrix, eTIMS ERP integration 2026 — https://www.greytrix.com/africa/integrating-e-invoices-with-erp-in-kenya-a-strategic-guide-for-2026-compliance/
- BetaSuite, eTIMS compliance guide — https://betasuiteerp.com/blog/kra-etims-compliance-guide-kenya
- People Daily, eTIMS and government procurement — https://peopledaily.digital/business/businesses-face-tighter-payment-checks-as-kra-links-etims-to-govt-procurement
- Odoo M-Pesa STK module (manual code fallback) — https://apps.odoo.com/apps/modules/17.0/pos_mpesa_stk
