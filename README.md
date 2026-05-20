# bank-spending-report

A [Claude Code](https://claude.ai/code) skill that analyses bank transaction CSV exports and produces a self-contained, printable HTML spending report. Hand it your CSV files and it will figure out what's real income vs recycled savings, identify reimbursements and pass-throughs, categorise spending, and produce charts with plain-English explanations.

Works with any bank's CSV export — the skill asks you about the column layout and adapts. Handles edge cases like savings recycling, investment outflows, group gift pass-throughs, and government/student allowance income.

## Installation

### Option 1 — Plugin marketplace (recommended)

In Claude Code:

```
/plugin marketplace add mludvig/bank-spending-report
/plugin install bank-spending-report@bank-spending-report
```

### Option 2 — Git clone

```bash
git clone https://github.com/mludvig/bank-spending-report ~/.claude/skills/bank-spending-report
```

Claude Code picks up skills from `~/.claude/skills/` automatically.

### Option 3 — Manual download

1. Download the ZIP from GitHub (Code → Download ZIP)
2. Extract it
3. Copy the extracted folder to `~/.claude/skills/bank-spending-report/`

The folder must contain `SKILL.md` at its root.

## Usage

Just mention bank transactions or spending analysis in your conversation:

> "Analyse my bank CSV and show me where my money goes"
> "Build a spending report for my son — here are his CSV exports"
> "I want to understand my spending habits over the last year"

Claude Code will trigger the skill automatically and walk you through the analysis.

## What you'll need

- Bank transaction export as CSV (most banks offer this under "Transaction history" or "Export")
- Opening account balance if it's not included in the CSV
- The account holder's name (for the report title)
- Optionally: account numbers for any family members or parents who send money (helps label income sources correctly)

## Output

- **`<name>_spending_report.html`** — self-contained report with embedded charts, printable to PDF via browser Ctrl+P → Save as PDF
- **`build_report_<name>.py`** — the analysis script, re-runnable if the CSV is updated

## Reference implementation

`references/build_report_example.py` is a complete working script from a real analysis (all personal details removed). Read it for implementation patterns — account numbers, category keywords, and reimbursement rules need replacing for each new person.

## License

Apache 2.0 — see [LICENSE](LICENSE).
