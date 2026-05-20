---
name: bank-spending-report
description: >
  Generate a printable HTML spending analysis report from bank CSV exports.
  Use this skill whenever someone wants to analyse their (or a family member's)
  bank transactions, understand spending patterns, see where money goes, build a
  spending report, review financial habits, or compare income vs spending over time.
  Trigger on phrases like: "analyse my bank CSV", "spending report", "where does
  my money go", "show me my spending habits", "financial summary from my bank",
  "make a report for my son/daughter", or any request involving bank transaction
  data and insights.
---

# Bank Spending Report

Generate a self-contained HTML spending analysis report from bank CSV exports.
The analysis script in `references/build_report_example.py` is a worked example
— adapt it for each person's specific accounts and situation, don't try to reuse
it as-is.

---

## The Core Question

Before writing a line of code, understand what you are actually measuring.

**Real income** = money that arrived from outside the person's own financial system.
**Real spending** = money that left and is genuinely gone.

Everything else — savings withdrawals, reimbursements, internal transfers,
investment round-trips — is noise that inflates both sides if you don't remove it.
Get this wrong and the numbers are meaningless.

---

## Phase 1 — Gather inputs

Ask the user for:
1. **CSV files** — main account plus any sub-accounts (savings, investments).
   Inspect the actual column names — they vary by bank and country.
2. **Opening balances** for each account if not in the CSV.
3. **Account owner's name** (for the report title).
4. **Who are the other people in this financial picture?** — parents, flatmates,
   partner, employer. Their account numbers let you label income sources correctly.
5. **Are there investment platforms?** (Sharesies, Hatch, InvestNow, Vanguard, etc.)
   Outflows to investments are wealth-building, not spending.
6. **Any known pass-throughs?** — did the person regularly pay for things on
   behalf of others and get reimbursed?

---

## Phase 2 — Map the money flows

Before categorising anything, classify each transaction by its *economic meaning*:

### Internal transfers
Moving money between the person's own accounts is neither income nor spending.
Detect by checking whether the destination/source account number belongs to the
account holder. If you have multiple CSV files, collect all `This Party Account`
values — those are the owner's own accounts.

### Savings recycling
If money flows: main account → savings → main account, the round-trip back is
**not new income**. It was already counted as income when it first arrived.
Exclude both the savings deposit (outflow) and the savings withdrawal (inflow)
from income and spending totals. Only the original deposit into the main account
counts — once.

### Reimbursement pass-throughs
The person paid for something on behalf of others and was paid back. Both sides
should be excluded — if you include just the spend without the reimbursement,
you overstate spending; if you include both sides, you inflate both income and
spending.

**How to detect them:** Look for an outflow followed shortly by an inflow of the
same or related amount, with a keyword in the reference/description suggesting
repayment ("petrol", "groceries", "gift", etc.). Group purchases (many small
equal inflows on the same day → one larger outflow) are a common pattern.

Use stable identifiers for matching, not row indices. Most banks include a
reference field with a unique transaction code per POS purchase — use that.
Bank transfers often share a generic reference ("INTERNET XFR"), so match those
by `(payee, amount, date)` tuples instead.

### Investment outflows
Transfers to investment platforms are wealth-building, not discretionary spending.
Flag them separately and report as a savings/investment metric, not as a spending
category.

### Government / institutional income
Student allowances, benefit payments, tax refunds — these are real income but
deserve their own label so the income breakdown is informative.

---

## Phase 3 — Interactive ambiguity resolution

**Don't guess silently.** Before computing final totals, surface what you don't know.

The goal here is to verify your assumptions with the person who actually knows
the context. A transaction that looks like income might be a one-off reimbursement.
A large outflow might be a group gift the person organised and was fully repaid for.

### What to flag

1. **Large one-offs** (top 5% by absolute value) with no obvious category — ask
   whether this was personal spend, a pass-through, or a gift.

2. **Recurring same-amount inflows** from unknown sources — could be wages,
   allowance, or regular reimbursements.

3. **Same-day clusters**: several small inflows from different people on the same
   day as a large outflow — classic group purchase.

4. **Investment-looking payees** — anything with "invest", "shares", "ETF",
   "fund" in the name. Confirm before classifying as spend.

5. **Payees appearing on both sides** — a payment platform (PayPal, Google) used
   for both buying and selling needs splitting.

Present findings as a numbered list and wait for answers before finalising.
Incorporate the responses before computing any totals.

---

## Phase 4 — Categorise spending

After resolving ambiguities, apply keyword matching on the payee name (lowercase).
First match wins. Build categories from what's actually in the data — don't force
categories that have no transactions.

Common useful categories:
- Food & Groceries (supermarkets, dairies, convenience stores)
- Fast Food / Takeaways
- Cafes & Coffee
- Restaurants
- Gaming & Subscriptions (streaming, games, apps)
- Transport (fuel, public transit, rideshare, parking)
- Shopping (clothing, pharmacy, hardware, general retail)
- Gifts & Presents (user-confirmed)
- Investments (confirmed investment platforms)
- Transfers to people (named individuals, user-confirmed)

After initial categorisation, print uncategorised transactions over a threshold
(e.g. $20) and ask whether any should be moved. Keep "Other" small — if it's
more than ~5% of total spend, dig into it with the user.

---

## Phase 5 — Compute what matters

### Income breakdown
For each income row, label the source:
- Known family/parent accounts → 'Family transfer'
- Chores / top-up apps → 'Family (chores / top-up)'
- Government agencies → 'Govt / StudyLink'
- Confirmed employer → 'Paid work'
- Investment platforms returning funds → exclude (not income)
- Unknown recurring amounts → resolve in Phase 3

### Key metrics to compute
- **Total real income** (external inflows only, after exclusions)
- **Total real spending** (external outflows only, after exclusions)
- **Surplus / deficit** — and whether it's structural or a one-off
- **Savings rate** = (savings deposits + investment outflows) / real income
- **Spending by category** — both totals and % of income
- **Monthly trend** — is spending going up, down, or flat?
- **End-of-day balance** — group by date, take the *last* transaction of each day.
  Never plot per-transaction balance — same-day ordering artefacts create false
  dips that don't reflect the actual end-of-day position.

### Drain analysis (only if relevant)
If the balance frequently hits near-zero before the next income arrives, compute:
- For each income event, how many days until the balance dropped below a threshold
  (e.g. ≤$1 or ≤10% of the post-income peak)
- Use **median** as the headline number — it's robust to the selection bias where
  fast-spenders drop out of later days, inflating the apparent mean
- Show n= counts on the x-axis so the reader can see the sample shrinking
- Explain the selection artefact in the caption

Skip this section if the person maintains a healthy buffer throughout.

---

## Phase 6 — Build the HTML report

Generate a single self-contained HTML file with all charts embedded as base64
PNG (matplotlib with `Agg` backend). No external dependencies. The file should
be printable to PDF via browser Ctrl+P → Save as PDF.

### Lead with the most striking insight

Open with 4 key stat cards. Choose based on the person's actual pattern:
- **Spender**: "X% of income on food/gaming", "median N days to nearly broke"
- **Saver**: "X% savings rate", "avg monthly surplus of $Y"

Don't lead with a metric that looks fine. Find the number that will make the
person think.

### Section order (adapt to what's interesting)

1. **Where the money goes** — category bar chart + top merchants table (20 rows)
2. **Impulse vs deliberate** — high-frequency / low-value transactions vs
   planned larger purchases
3. **Monthly income vs spending** — side-by-side bars + rolling average trend
4. **Savings & investments** — cumulative chart, "what if" simulation at 10/20/30%
   savings rate if currently low, or "keep it up" message if healthy
5. **Balance over time** — end-of-day balance with annotated income events
6. **Drain analysis** — only if relevant (see Phase 5)

Add `style="page-break-before:always;"` to `<h2>` tags that start new major
sections to prevent orphan headers when printing.

### Tone
Write for the report subject, not a data scientist. Plain English. Be direct —
if spending is a problem, say so. If savings are healthy, show how to build on
it. Charts need captions that explain what the chart means, not just what it shows.

### Print CSS
Include an `@media print` block:
- Dark stat cards → white background, coloured border, dark text
- Alert/insight boxes → white background, coloured left border preserved
- Table headers → light grey, dark text
- Use `print-color-adjust: exact` on coloured badges

### matplotlib legend
Always construct explicit `Line2D`/`Patch` objects for legend handles — never
reference `ax.lines[N]` or `ax.collections[N]`. These produce `_child0` labels
in the legend.

---

## Phase 7 — Deliver

Save the report as `<name>_spending_report.html` in the working directory.
Also save the analysis script as `build_report_<name>.py` — the script should
be self-contained and re-runnable if the CSV is updated.

Confirm both file paths to the user.

---

## Reference implementation

`references/build_report_example.py` is a complete working script from a prior
analysis. It demonstrates the data pipeline, reimbursement detection, category
rules, chart generation, and HTML assembly. Read it for implementation patterns,
but adapt everything — account numbers, category keywords, person name, and
reimbursement rules must all be replaced for each new person.

Key things the example shows that are easy to get wrong:
- Sort by `Date` only — not `Date` + account name. Mixed sort orders make any
  row-based matching unreliable.
- Use Reference strings (unique POS terminal+timestamp codes) for stable
  reimbursement matching. Use `(payee, amount, date)` tuples for bank transfers
  that share generic references.
- Reconciliation check: opening balance + external inflows + external outflows
  ≈ actual ending balance. If off by more than ~$5, investigate before finalising.
