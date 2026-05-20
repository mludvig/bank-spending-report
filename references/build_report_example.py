"""
build_report_example.py — reference implementation for bank-spending-report skill

Generates a self-contained HTML spending analysis report from NZ bank CSV exports.
All charts are embedded as base64 PNG (matplotlib Agg backend) — no external dependencies.

HOW TO USE THIS FILE:
  This is a worked example / reference implementation. To adapt it for a real analysis:
  1. Replace OPENING, MAIN_ACCOUNT, ACCOUNT_FILES with actual values.
  2. Update PERSON_NAME to the account holder's name.
  3. Review REIMB_REFS and is_reimbursed_row() — add any reimbursed pass-throughs.
  4. Review label_source() — update account number fragments and payee names.
  5. Review the 'Transfers Out' row in category_rules — replace with actual friend names.
  6. Run: uv run build_report_example.py
"""
import base64, io, json
from datetime import timedelta

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ── Style ──────────────────────────────────────────────────────────────────
REPORT_PALETTE = {
    'income':      '#2ecc71',
    'spend':       '#e74c3c',
    'balance':     '#2980b9',
    'highlight':   '#f39c12',
    'gaming':      '#9b59b6',
    'cafes':       '#f1c40f',
    'fastfood':    '#e67e22',
    'snacks':      '#e74c3c',
    'restaurants': '#c0392b',
    'shopping':    '#1abc9c',
    'transport':   '#7f8c8d',
    'transfers':   '#bdc3c7',
    'other':       '#95a5a6',
    'neutral':     '#34495e',
    'grid':        '#ecf0f1',
}

plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor':   'white',
    'axes.edgecolor':   '#cccccc',
    'axes.grid':        True,
    'grid.color':       '#eeeeee',
    'grid.linewidth':   0.8,
    'font.family':      'DejaVu Sans',
    'font.size':        11,
    'axes.titlesize':   13,
    'axes.titleweight': 'bold',
    'axes.labelsize':   11,
    'xtick.labelsize':  10,
    'ytick.labelsize':  10,
    'legend.fontsize':  10,
})

def fig_to_b64(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def img_tag(b64, alt='', width='100%'):
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="width:{width};max-width:100%;">'

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION  — replace these values for each analysis
# ═══════════════════════════════════════════════════════════════════════════

# Replace with actual account numbers and opening balances.
# These are the balances at the START of the analysis period (not always in the CSV).
OPENING = {
    '02-XXXX-XXXXXXX-XX': 0.00,   # Main spending account
    '02-XXXX-XXXXXXX-XX': 0.00,   # Hidden savings sub-account
    '02-XXXX-XXXXXXX-XX': 0.00,   # Savings account
}

# The main account to build the per-transaction balance series for.
# Must match one of the keys in OPENING above.
MAIN_ACCOUNT = '02-XXXX-XXXXXXX-XX'

OWNER_ACCOUNTS = set(OPENING.keys())

# Map each account number to its downloaded CSV filename.
ACCOUNT_FILES = {
    '02-XXXX-XXXXXXX-XX': 'Main-Account.csv',
    '02-XXXX-XXXXXXX-XX': 'Hidden-Savings.csv',
    '02-XXXX-XXXXXXX-XX': 'Savings.csv',
}

# Name shown in the report title and output filename.
PERSON_NAME = "Name"

# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════
frames = []
for acct, fname in ACCOUNT_FILES.items():
    tmp = pd.read_csv(fname, parse_dates=['Date'], dayfirst=True)
    tmp.columns = tmp.columns.str.strip()
    tmp['file_account'] = acct
    frames.append(tmp)

all_txns = pd.concat(frames, ignore_index=True).sort_values('Date').reset_index(drop=True)
all_txns['Other Party Account'] = all_txns['Other Party Account'].fillna('').str.strip()
all_txns['Amount'] = pd.to_numeric(all_txns['Amount'], errors='coerce').fillna(0)
all_txns['Payee']  = all_txns['Payee'].fillna('').str.strip()

all_txns['is_internal'] = all_txns['Other Party Account'].isin(OWNER_ACCOUNTS)
all_txns['is_self_interest'] = (
    all_txns['Other Party Account'] == all_txns['This Party Account']
)
all_txns['is_external'] = ~all_txns['is_internal']

def label_source(row):
    """
    Classify each external income row with a human-readable source label.

    Update the account number fragments (e.g. 'XXXXXXX-00') and payee names
    to match the actual parent/guardian accounts and income sources in your data.

    Example patterns:
      - A YouMoney top-up platform account has a recognisable account suffix.
      - Direct bank transfers from known individuals match on Payee name.
      - Paid work (property management, modelling agency, etc.) matches on Payee keyword.
      - Government payments (IRD, StudyLink, MSD) match on 'I.R.D', 'StudyLink', etc.
    """
    payee = row['Payee']
    other = row['Other Party Account']
    # Replace 'XXXXXXX-00' etc. with actual account number fragments.
    # Replace 'YouMoney', 'Savings', 'PARENT/LASTNAME' with actual payee strings.
    if 'XXXXXXX-00' in other or payee == 'YouMoney':     return 'Parents (YouMoney)'
    if 'XXXXXXX-01' in other or payee == 'Savings':      return 'Parents (Savings acct)'
    if 'XXXXXXX-07' in other or payee in ('PARENT/LASTNAME', 'Parent Name'): return 'Parents (direct)'
    # Replace with actual employer or work-source payee names.
    if payee in ('Employer Name', 'PROPERTY TRUST'):     return 'Paid work (property)'
    if 'AGENCY NAME' in payee:                           return 'Agency (gig income)'
    if 'I.R.D' in payee:                                 return 'IRD (govt payment)'
    if row.get('is_self_interest'):                      return 'Interest'
    return 'Friends / other'

all_txns['income_source'] = all_txns.apply(label_source, axis=1)

df = all_txns[all_txns['file_account'] == MAIN_ACCOUNT].copy().reset_index(drop=True)
OPENING_BALANCE = OPENING[MAIN_ACCOUNT]
df['Balance'] = OPENING_BALANCE + df['Amount'].cumsum()

# Update 'Savings Account Name' to match the Payee string used by the savings sub-account.
df['is_savings_deposit']    = (df['Amount'] < 0) & df['Payee'].str.contains('Savings Account Name', case=False)
df['is_savings_withdrawal'] = (df['Amount'] > 0) & df['Payee'].str.contains('Savings Account Name', case=False)

# ── Reimbursed pass-through detection ───────────────────────────────────────
#
# Some transactions are pass-throughs: the account holder paid on behalf of
# others and was later reimbursed. Exclude both sides from spending/income totals.
#
# Detection strategy:
#   Primary:  Reference field — unique POS terminal + timestamp string
#             (e.g. '492102232056'). Add any confirmed reimbursed POS spend rows here.
#   Fallback: (payee, particulars, amount) tuples for bank transfers, which all
#             share 'INTERNET XFR' as their Reference value.
#
# Build this set during Phase 3 interactive review as the user confirms each item.
REIMB_REFS = {
    # Petrol spends (replace with actual Reference codes from the CSV)
    # '492102232056',  # DD Mon YY  Petrol station  -$XX.XX
    # '492102291748',  # DD Mon YY  Petrol station  -$XX.XX

    # Clothing / haircut spends
    # '420549141431',  # DD Mon YY  Clothing store  -$XX.XX
    # '434667111119',  # DD Mon YY  Haircut         -$XX.XX

    # Group gift: N friends contributed $XX each toward a group gift;
    # account holder organised and bought through a single merchant.
    # '420549231801',  # DD Mon YY  Gift merchant   -$XXX.XX
}

def is_reimbursed_row(row):
    """
    Return True if this row should be treated as a reimbursed pass-through.

    Two detection paths:
      1. Reference match — for POS transactions where Reference is a unique
         terminal + timestamp code (see REIMB_REFS above).
      2. (payee, particulars, amount) match — for bank transfers, which share
         'INTERNET XFR' as their Reference value. Add specific tuples here once
         confirmed with the user.

    Common patterns to look for:
      - Petrol reimbursements: a large fuel outflow followed by a YouMoney
        inflow with a 'Petrol' or similar keyword in Particulars.
      - Haircut / clothing: specific store outflow + YouMoney inflow with
        'Haircut' or 'Clothing' keyword in Particulars.
      - Group gifts: multiple friends (Friend A, Friend B, Friend C) each send
        an equal amount (e.g. $25) on the same day, immediately followed by a
        single purchase for roughly that total (e.g. $100 from a gift merchant).
        Exclude both the individual inflows and the group purchase outflow.
    """
    ref = row.get('Reference')
    if pd.notna(ref) and str(ref) in REIMB_REFS:
        return True
    payee = row['Payee']
    amt   = row['Amount']
    parts = str(row.get('Particulars', ''))
    date  = row['Date']

    # Petrol reimbursements via YouMoney (replace 'Petrol' with actual Particulars keyword)
    if payee == 'YouMoney' and 'Petrol' in parts and amt > 0:
        return True

    # Clothing/haircut reimbursements via YouMoney or Savings
    # (replace keyword list with actual Particulars values seen in the data)
    if payee == 'YouMoney' and any(kw in parts for kw in ('Haircut', 'Clothing', 'Sport')):
        return True
    if payee == 'Savings' and 'Haircut' in parts and amt == 0.00:  # replace 0.00 with actual amount
        return True

    # Group gift pass-through detection:
    # On a specific date, N friends each sent the same amount. Replace the date,
    # amount, and payee names with the actual values confirmed during review.
    # Example: 5 friends sent $25 each on the same day for a group gift.
    #
    # if (date == pd.Timestamp('YYYY-MM-DD') and amt == 25.0
    #         and payee in ('Friend A', 'Friend B', 'Friend C')):
    #     return True

    return False

df['is_reimbursed'] = df.apply(is_reimbursed_row, axis=1)
df['is_income'] = (df['Amount'] > 0) & ~df['is_savings_deposit'] & ~df['is_reimbursed']
df['is_spend']  = (df['Amount'] < 0) & ~df['is_savings_deposit'] & ~df['is_reimbursed']

_reimb_pairs = set(zip(df[df['is_reimbursed']]['Date'], df[df['is_reimbursed']]['Amount']))
all_txns['is_reimbursed_passthrough'] = all_txns.apply(
    lambda r: r['file_account'] == MAIN_ACCOUNT
              and (r['Date'], r['Amount']) in _reimb_pairs, axis=1)
all_txns['is_external_income'] = (all_txns['is_external'] & (all_txns['Amount'] > 0)
                                   & ~all_txns['is_reimbursed_passthrough'])
all_txns['is_external_spend']  = (all_txns['is_external'] & (all_txns['Amount'] < 0)
                                   & ~all_txns['is_reimbursed_passthrough'])

# ── Episodes ────────────────────────────────────────────────────────────────
income_rows = df[df['is_income']].copy()
episodes = []
for i, (idx, row) in enumerate(income_rows.iterrows()):
    start_date       = row['Date']
    bal_after_income = row['Balance']
    if i + 1 < len(income_rows):
        next_income_date = income_rows.iloc[i + 1]['Date']
    else:
        next_income_date = df['Date'].max() + timedelta(days=1)
    window = df[(df.index > idx) & (df['Date'] < next_income_date) & df['is_spend']].copy()
    total_spent = window['Amount'].abs().sum()
    min_balance = df[(df.index >= idx) & (df['Date'] < next_income_date)]['Balance'].min()
    went_broke  = min_balance <= 1.0
    days_to_broke = None
    if went_broke:
        broke_rows = df[(df.index > idx) & (df['Date'] < next_income_date) & (df['Balance'] <= 1.0)]
        if not broke_rows.empty:
            days_to_broke = (broke_rows.iloc[0]['Date'] - start_date).days
    episodes.append({
        'start_date':          start_date,
        'income_amount':       row['Amount'],
        'balance_after_income':bal_after_income,
        'next_income_date':    next_income_date,
        'days_to_broke':       days_to_broke,
        'total_spent':         total_spent,
        'min_balance':         min_balance,
        'went_broke':          went_broke,
        'payee':               row['Payee'],
        'particulars':         row.get('Particulars',''),
    })

episodes_df = pd.DataFrame(episodes)
bal_75th = episodes_df['balance_after_income'].quantile(0.75)
episodes_df['is_outlier'] = (
    (episodes_df['balance_after_income'] > bal_75th) &
    (episodes_df['days_to_broke'].isna() | (episodes_df['days_to_broke'] > 7))
)
normal   = episodes_df[~episodes_df['is_outlier']].copy()
broke_episodes = normal[normal['went_broke'] & normal['days_to_broke'].notna()].copy()

# ── Categories ──────────────────────────────────────────────────────────────
# Customise these keywords to match the actual merchants in the data.
# Add or remove keywords as needed after reviewing the transaction list.
# First matching rule wins — more specific rules should come before broader ones.
category_rules = [
    ('Food & Snacks',    ['woolworths', 'new world', 'paknsave', 'pak n save', 'countdown', 'dairy',
                          'mini mart', 'station mart', 'circle k', 'four square', 'freshchoice',
                          'd h supermarket', 'superfood', 'avondale food', 'exotic candy',
                          'woodlands park', 'waima', 'westview', 'superette', 'juice up',
                          'fresh choice', 'fruit shop', 'fruit world', 'golf road']),
    ('Fast Food',        ['mcdonald', 'mcdonalds', 'domino', 'burger king', 'kfc', 'subway',
                          'pizza', 'sals', 'gong cha', 'chatime', 'boost juice',
                          'popeyes', 'hungry jack', 'wendys', 'order meal', 'doordash']),
    ('Cafes & Bakeries', ['levain', 'cafeteria', 'daily dojo', 'bakery', 'baker', 'cafe',
                          'coffee', 'dc caterers', 'caterer', 'kitchen', 'ronnie', 'crafty baker',
                          'mae nam', 'chocolates', 'taranaki', 'smokos', 'coffix', 'tramcar',
                          'chill out thai', 'chaska', 'the social room', 'coles']),
    ('Gifts & Presents', ['takapuna buffet', 'janken']),
    ('Restaurants',      ['best sushi', 'goldenbridge', 'o bowl', "st pierre", 'mai sushi',
                          'katsubi', 'matsu sushi', 'umiya sushi', 'seoulmate',
                          'tb brickworks', 'evans kebab',
                          'nz kebab', 'monster kebab', 'titirangi takeaway',
                          'green bay takeaway', 'king of kings', 'kiwiyo',
                          'toro churro', 'hks manawa', 'xin fu', 'xin rong',
                          'japan mart', 'hulucat', 'pa tea', 'tang tea', 'wenly',
                          'the chicken', 'blockhouse bay fish', 'rusi cane',
                          'devonport', 'restaurant', 'sals pizza', 'reading cinemas']),
    ('Gaming & Subs',    ['twitch', 'rblx', 'supercell', 'epc*fortnite', 'kiss anime',
                          'crunchyroll', 'steamgames', 'steam', 'eb games', 'u7buy',
                          'nyx*pokesiho', 'paypal *lime', 'getnomad',
                          'netflix', 'spotify', 'google', 'apple', 'timezone']),
    ('Transport',        ['uber', 'lyft', 'at hop', 'parking', 'z point', 'tasman fuel',
                          'z green bay', '7-eleven']),
    # Replace these payee names with the actual friend/family names seen in the data.
    ('Transfers Out',    ['friend one', 'friend two', 'friend three', 'sibling name']),
    ('Shopping',         ['whitcoulls', 'the warehouse', 'acquisitions', 'chemist warehouse',
                          'mitre 10', 'look sharp', 'dollar outlet', 'old lolly shop',
                          'secret garden', 'lil orbits', 'bounce', 'iticket', 'lilliputts',
                          'custom mart', 'hashim trading']),
]

def assign_category(payee):
    p = str(payee).lower()
    for cat, keywords in category_rules:
        if any(kw in p for kw in keywords):
            return cat
    return 'Other'

spend_df = df[df['is_spend']].copy()
spend_df = spend_df[~spend_df['Payee'].str.upper().isin(['WITHDRAWAL','ATM WITHDRAWAL'])]
spend_df['Category'] = spend_df['Payee'].apply(assign_category)

# ── Key numbers ─────────────────────────────────────────────────────────────
total_real_income = all_txns[all_txns['is_external_income']]['Amount'].sum()
total_real_spend  = spend_df['Amount'].abs().sum()
cat_summary = spend_df.groupby('Category')['Amount'].agg(
    total=lambda x: x.abs().sum(), count='count').sort_values('total', ascending=False)
food_cats = ['Food & Snacks','Fast Food','Cafes & Bakeries','Restaurants']
food_total = cat_summary.loc[cat_summary.index.isin(food_cats), 'total'].sum()
gaming_total = cat_summary.loc['Gaming & Subs','total'] if 'Gaming & Subs' in cat_summary.index else 0
impulse_cats = ['Food & Snacks','Fast Food','Cafes & Bakeries','Gaming & Subs']
impulse_total = cat_summary.loc[cat_summary.index.isin(impulse_cats), 'total'].sum()
pct_went_broke = 100 * len(broke_episodes) / len(normal)
median_days = broke_episodes['days_to_broke'].median()

TODAY_SIM   = pd.Timestamp('2026-05-19')
ANNUAL_RATE = 0.05
income_events = all_txns[all_txns['is_external_income']][['Date','Amount']].copy()
income_events.columns = ['date','amount']
opening_total = sum(OPENING.values())
opening_row   = pd.DataFrame([{'date': pd.Timestamp('2024-05-18'), 'amount': opening_total}])
income_events = pd.concat([opening_row, income_events], ignore_index=True).sort_values('date').reset_index(drop=True)

savings_results = {}
for frac in [0.10, 0.20, 0.30]:
    balance = 0.0
    for _, row_s in income_events.iterrows():
        years = (TODAY_SIM - row_s['date']).days / 365.25
        balance += row_s['amount'] * frac * ((1 + ANNUAL_RATE) ** years)
    savings_results[frac] = balance

# ═══════════════════════════════════════════════════════════════════════════
# CHART 1 — Running balance (end-of-day, so intra-day ordering doesn't dip)
# ═══════════════════════════════════════════════════════════════════════════
# Use end-of-day balance: last transaction row for each calendar day
eod = df.groupby('Date')['Balance'].last().reset_index()

fig, ax = plt.subplots(figsize=(14, 4.5))
ax.fill_between(eod['Date'], eod['Balance'], alpha=0.12, color=REPORT_PALETTE['balance'])
ax.plot(eod['Date'], eod['Balance'], color=REPORT_PALETTE['balance'], linewidth=1.2)
ax.axhline(1, color=REPORT_PALETTE['spend'], linestyle='--', linewidth=1.2, label='$1 (effectively broke)')

# Shade high-balance / windfall periods (excluded from pattern stats)
outlier_eps = episodes_df[episodes_df['is_outlier']]
for _, ep in outlier_eps.iterrows():
    ax.axvspan(ep['start_date'], ep['next_income_date'], alpha=0.12, color=REPORT_PALETTE['highlight'], zorder=0)

# Mark income events at end-of-day balance for that date
income_dates = df[df['is_income']]['Date'].unique()
income_eod = eod[eod['Date'].isin(income_dates)]
ax.scatter(income_eod['Date'], income_eod['Balance'],
           color=REPORT_PALETTE['income'], s=18, zorder=5, label='Money in (end of day)', alpha=0.8)

from matplotlib.patches import Patch
from matplotlib.lines import Line2D
legend_handles = [
    Line2D([0], [0], color=REPORT_PALETTE['spend'], linestyle='--', linewidth=1.2,
           label='$1 (effectively broke)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=REPORT_PALETTE['income'],
           markersize=7, label='Money in (end of day)'),
    Patch(facecolor=REPORT_PALETTE['highlight'], alpha=0.5,
          label='High-balance periods (excluded from pattern stats)'),
]
ax.legend(handles=legend_handles, loc='upper left', framealpha=0.9)

ax.set_title('Account Balance — May 2024 to May 2026')
ax.set_ylabel('Balance ($)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
fig.autofmt_xdate(rotation=30)
fig.tight_layout()
CHART_BALANCE = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 1b — Broke days: timeline + monthly count
# ═══════════════════════════════════════════════════════════════════════════
# Build a complete daily series by forward-filling end-of-day balances
all_dates = pd.date_range(eod['Date'].min(), eod['Date'].max(), freq='D')
daily = eod.set_index('Date').reindex(all_dates).ffill().reset_index()
daily.columns = ['Date', 'Balance']
daily['broke'] = daily['Balance'] <= 1.0

broke_days_total = daily['broke'].sum()

# Monthly broke-day counts
daily['YearMonth'] = daily['Date'].dt.to_period('M')
monthly_broke = daily.groupby('YearMonth')['broke'].sum().reset_index()
monthly_broke.columns = ['YearMonth', 'broke_days']
monthly_broke['YearMonth_dt'] = monthly_broke['YearMonth'].dt.to_timestamp()
# Days in each month (for %)
monthly_broke['days_in_month'] = monthly_broke['YearMonth'].apply(lambda p: p.days_in_month)
monthly_broke['pct'] = 100 * monthly_broke['broke_days'] / monthly_broke['days_in_month']

fig, axes = plt.subplots(2, 1, figsize=(14, 7),
                         gridspec_kw={'height_ratios': [1.6, 1], 'hspace': 0.12})

# Top: daily balance with broke days highlighted
ax = axes[0]
ax.fill_between(daily['Date'], daily['Balance'], alpha=0.12, color=REPORT_PALETTE['balance'])
ax.plot(daily['Date'], daily['Balance'], color=REPORT_PALETTE['balance'], linewidth=1.0)
# Shade every broke day red
broke_runs = []
in_run, run_start = False, None
for _, row_d in daily.iterrows():
    if row_d['broke'] and not in_run:
        in_run, run_start = True, row_d['Date']
    elif not row_d['broke'] and in_run:
        broke_runs.append((run_start, row_d['Date']))
        in_run = False
if in_run:
    broke_runs.append((run_start, daily['Date'].iloc[-1]))
for start_r, end_r in broke_runs:
    ax.axvspan(start_r, end_r + pd.Timedelta(days=1),
               color=REPORT_PALETTE['spend'], alpha=0.35, zorder=2, linewidth=0)
ax.axhline(1, color=REPORT_PALETTE['spend'], linestyle='--', linewidth=1.0, alpha=0.6)
ax.set_ylabel('Balance ($)')
ax.set_title(f'Daily Balance — red bands = days with ≤$1 ({broke_days_total} days total over 2 years)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax.set_xticklabels([])
ax.set_xlim(daily['Date'].min(), daily['Date'].max())

# Bottom: monthly broke-day bar chart
ax2 = axes[1]
bar_colors = [REPORT_PALETTE['spend'] if d > 0 else REPORT_PALETTE['neutral']
              for d in monthly_broke['broke_days']]
bars = ax2.bar(monthly_broke['YearMonth_dt'], monthly_broke['broke_days'],
               color=bar_colors, width=20, edgecolor='white', linewidth=0.5)
# Annotate bars with day count where > 0
for bar, val in zip(bars, monthly_broke['broke_days']):
    if val > 0:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.15,
                 str(int(val)), ha='center', va='bottom', fontsize=8.5, color='#333')
avg_broke = monthly_broke['broke_days'].mean()
ax2.axhline(avg_broke, color='#888', linestyle='--', linewidth=1.2,
            label=f'Monthly avg {avg_broke:.1f} days')
ax2.set_ylabel('Broke days / month')
ax2.set_xlabel('')
ax2.set_xlim(daily['Date'].min(), daily['Date'].max())
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax2.yaxis.set_major_locator(mticker.MultipleLocator(2))
ax2.legend(loc='upper right', fontsize=9)
fig.autofmt_xdate(rotation=30)
fig.tight_layout()
CHART_BROKE_DAYS = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 2 — Days to broke: histogram + CDF
# ═══════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

ax = axes[0]
bins = np.arange(-0.5, broke_episodes['days_to_broke'].max() + 1.5, 1)
ax.hist(broke_episodes['days_to_broke'], bins=bins, color=REPORT_PALETTE['spend'],
        edgecolor='white', linewidth=0.8)
ax.set_title('How Many Days to Reach $1?')
ax.set_xlabel('Days after money arrived')
ax.set_ylabel('Number of episodes')
ax.xaxis.set_major_locator(mticker.MultipleLocator(1))

ax = axes[1]
sorted_days = np.sort(broke_episodes['days_to_broke'])
cdf = np.arange(1, len(sorted_days)+1) / len(normal)  # fraction of ALL normal episodes
ax.plot(sorted_days, cdf * 100, color=REPORT_PALETTE['spend'], linewidth=2.2)
ax.fill_between(sorted_days, cdf * 100, alpha=0.15, color=REPORT_PALETTE['spend'])
for pct, label in [(50,'50%'),(75,'75%')]:
    idx_cross = np.searchsorted(cdf * 100, pct)
    if idx_cross < len(sorted_days):
        day_val = sorted_days[idx_cross]
        ax.axvline(day_val, color='#888', linestyle=':', linewidth=1)
        ax.axhline(pct,     color='#888', linestyle=':', linewidth=1)
        ax.annotate(f'{pct}% by day {day_val:.0f}',
                    xy=(day_val, pct), xytext=(day_val + 0.5, pct - 5),
                    fontsize=9.5, color='#444')
ax.set_title('Cumulative: % of All Episodes Broke by Day X')
ax.set_xlabel('Days after money arrived')
ax.set_ylabel('% of normal episodes drained')
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))
ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
fig.tight_layout()
CHART_BROKE = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 3 — Average drain curve
# ═══════════════════════════════════════════════════════════════════════════
episode_trajectories = []
for _, ep in normal[normal['went_broke']].iterrows():
    start = ep['start_date']
    end   = ep['next_income_date']
    peak  = ep['balance_after_income']
    if peak <= 0:
        continue
    window = df[(df['Date'] >= start) & (df['Date'] < end)].copy()
    window['day_offset'] = (window['Date'] - start).dt.days
    for day in range(15):
        day_rows = window[window['day_offset'] == day]
        if not day_rows.empty:
            bal = day_rows.iloc[-1]['Balance']
            episode_trajectories.append({'day': day, 'pct_remaining': 100 * bal / peak})

traj_df = pd.DataFrame(episode_trajectories)
traj_stats = traj_df.groupby('day')['pct_remaining'].agg(['mean','std','median','count']).reset_index()

fig, ax = plt.subplots(figsize=(10, 4.5))

# ±1 std dev band around the mean
ax.fill_between(traj_stats['day'],
                (traj_stats['mean'] - traj_stats['std']).clip(0),
                (traj_stats['mean'] + traj_stats['std']).clip(0, 100),
                alpha=0.12, color=REPORT_PALETTE['spend'])

# Mean — thinner, secondary
ax.plot(traj_stats['day'], traj_stats['mean'], color=REPORT_PALETTE['spend'],
        linewidth=1.4, linestyle='--', alpha=0.7, label='Mean balance')

# Median — primary, bold; more robust because fast-spending episodes that hit $0
# first drop out of the sample, which inflates the mean but barely moves the median
ax.plot(traj_stats['day'], traj_stats['median'], color=REPORT_PALETTE['balance'],
        linewidth=2.4, label='Median balance (more reliable)')

# Annotate episode count per day so the shrinking sample is transparent
for _, r in traj_stats.iterrows():
    if r['count'] > 0:
        ax.text(r['day'], -4, f"n={int(r['count'])}", ha='center', fontsize=7.5, color='#999')

ax.axhline(0, color='black', linewidth=0.8)
ax.set_title('Balance After Money Arrives — % of starting amount (episodes that went broke)')
ax.set_xlabel('Days since money arrived')
ax.set_ylabel('Balance remaining (%)')
ax.set_xlim(-0.3, traj_stats['day'].max() + 0.3)
ax.set_ylim(bottom=-8)
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))
ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
ax.legend(loc='upper right', fontsize=9)
fig.tight_layout()
CHART_DRAIN = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 4 — Category breakdown (bar, not pie — easier to read exact amounts)
# ═══════════════════════════════════════════════════════════════════════════
cat_colors_map = {
    'Food & Snacks':    REPORT_PALETTE['snacks'],
    'Fast Food':        REPORT_PALETTE['fastfood'],
    'Cafes & Bakeries': REPORT_PALETTE['cafes'],
    'Restaurants':      REPORT_PALETTE['restaurants'],
    'Gaming & Subs':    REPORT_PALETTE['gaming'],
    'Shopping':         REPORT_PALETTE['shopping'],
    'Gifts & Presents': '#e91e8c',
    'Transfers Out':    REPORT_PALETTE['transfers'],
    'Transport':        REPORT_PALETTE['transport'],
    'Other':            REPORT_PALETTE['other'],
}
cat_plot = cat_summary.sort_values('total', ascending=True)

fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={'width_ratios': [1.6, 1]})

# Left: horizontal bar chart
ax = axes[0]
colors = [cat_colors_map.get(c, '#95a5a6') for c in cat_plot.index]
bars = ax.barh(cat_plot.index, cat_plot['total'], color=colors, edgecolor='white', height=0.7)
for bar, val in zip(bars, cat_plot['total']):
    ax.text(bar.get_width() + 15, bar.get_y() + bar.get_height()/2,
            f'${val:,.0f}', va='center', ha='left', fontsize=10, color='#333')
ax.set_title('Total Spending by Category (2 years)')
ax.set_xlabel('Total spent ($)')
ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax.set_xlim(right=cat_plot['total'].max() * 1.20)
ax.grid(axis='y', alpha=0)
ax.grid(axis='x', alpha=0.4)

# Right: pie for food vs rest
ax2 = axes[1]
food_val   = cat_summary.loc[cat_summary.index.isin(food_cats), 'total'].sum()
gaming_val = cat_summary.loc['Gaming & Subs','total'] if 'Gaming & Subs' in cat_summary.index else 0
other_food_val = total_real_spend - food_val - gaming_val
wedges, texts, autotexts = ax2.pie(
    [food_val, gaming_val, other_food_val],
    labels=['All Food\n(4 categories)', 'Gaming &\nSubs', 'Everything\nelse'],
    colors=[REPORT_PALETTE['spend'], REPORT_PALETTE['gaming'], REPORT_PALETTE['neutral']],
    autopct='%1.0f%%', startangle=90, pctdistance=0.75,
    wedgeprops=dict(edgecolor='white', linewidth=2))
for at in autotexts:
    at.set_fontsize(12)
    at.set_fontweight('bold')
    at.set_color('white')
ax2.set_title(f'Food + Gaming vs Everything Else\n(Total spent: ${total_real_spend:,.0f})')
fig.tight_layout()
CHART_CATS = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 5 — Impulse monthly frequency + top merchants
# ═══════════════════════════════════════════════════════════════════════════
impulse_df = spend_df[spend_df['Category'].isin(impulse_cats)].copy()
impulse_df['YearMonth'] = impulse_df['Date'].dt.to_period('M')
monthly_imp = impulse_df.groupby(['YearMonth','Category'])['Amount'].agg(
    total=lambda x: x.abs().sum(), count='count').reset_index()
monthly_imp['YearMonth_dt'] = monthly_imp['YearMonth'].dt.to_timestamp()

all_months = sorted(monthly_imp['YearMonth'].unique())
cat_imp_colors = {
    'Food & Snacks':    REPORT_PALETTE['snacks'],
    'Fast Food':        REPORT_PALETTE['fastfood'],
    'Cafes & Bakeries': REPORT_PALETTE['cafes'],
    'Gaming & Subs':    REPORT_PALETTE['gaming'],
}
imp_monthly_wide = monthly_imp.pivot_table(index='YearMonth_dt', columns='Category',
                                            values='total', fill_value=0)

# Top 15 merchants within impulse cats
top_merch = (impulse_df.groupby('Payee')['Amount']
             .agg(lambda x: x.abs().sum())
             .sort_values(ascending=False)
             .head(12))

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Left: stacked monthly
ax = axes[0]
bottom = np.zeros(len(imp_monthly_wide))
for cat in ['Food & Snacks','Fast Food','Cafes & Bakeries','Gaming & Subs']:
    if cat in imp_monthly_wide.columns:
        vals = imp_monthly_wide[cat].values
        ax.bar(imp_monthly_wide.index, vals, bottom=bottom,
               color=cat_imp_colors[cat], label=cat, width=20)
        bottom += vals
avg_total = imp_monthly_wide.sum(axis=1).mean()
ax.axhline(avg_total, color='#333', linewidth=1.4, linestyle='--',
           label=f'Monthly avg ${avg_total:.0f}')
ax.set_title('Monthly Impulse Spend by Category')
ax.set_ylabel('Amount ($)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
fig.autofmt_xdate(rotation=30)
ax.legend(loc='upper left', fontsize=9)
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))

# Right: top merchants horizontal bar
ax2 = axes[1]
merch_colors = []
for p in top_merch.index:
    cat = assign_category(p)
    merch_colors.append(cat_imp_colors.get(cat, REPORT_PALETTE['other']))
bars2 = ax2.barh(
    [p[:28] for p in top_merch.index[::-1]],
    top_merch.values[::-1],
    color=merch_colors[::-1], edgecolor='white', height=0.7)
for bar, val in zip(bars2, top_merch.values[::-1]):
    ax2.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2,
             f'${val:.0f}', va='center', fontsize=9, color='#333')
ax2.set_title('Top 12 Impulse Merchants (2-year total)')
ax2.set_xlabel('Total spent ($)')
ax2.xaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax2.set_xlim(right=top_merch.max() * 1.22)
ax2.grid(axis='y', alpha=0)
fig.tight_layout()
CHART_IMPULSE = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 6 — Monthly income vs spend
# ═══════════════════════════════════════════════════════════════════════════
spend_df['YearMonth'] = spend_df['Date'].dt.to_period('M')
monthly_spend = spend_df.groupby('YearMonth')['Amount'].agg(lambda x: x.abs().sum()).reset_index()
monthly_spend.columns = ['YearMonth','spend']

income_df_m = df[df['is_income']].copy()
income_df_m['YearMonth'] = income_df_m['Date'].dt.to_period('M')
monthly_inc = income_df_m.groupby('YearMonth')['Amount'].sum().reset_index()
monthly_inc.columns = ['YearMonth','income']

monthly = pd.merge(monthly_spend, monthly_inc, on='YearMonth', how='outer').fillna(0)
monthly = monthly[monthly['YearMonth'] < pd.Period('2026-05','M')].copy()
monthly['YearMonth_dt'] = monthly['YearMonth'].dt.to_timestamp()
monthly['roll_spend'] = monthly['spend'].rolling(3, min_periods=1).mean()

fig, ax = plt.subplots(figsize=(14, 4.5))
x = np.arange(len(monthly))
w = 0.4
bars_i = ax.bar(x - w/2, monthly['income'], width=w, color=REPORT_PALETTE['income'],
                alpha=0.85, label='Income', zorder=3)
bars_s = ax.bar(x + w/2, monthly['spend'],  width=w, color=REPORT_PALETTE['spend'],
                alpha=0.85, label='Spending', zorder=3)
ax.plot(x + w/2, monthly['roll_spend'], color='#8e1a1a', linewidth=2,
        label='3-month rolling avg spend', zorder=4)
ax.set_xticks(x)
ax.set_xticklabels([str(p)[:7] for p in monthly['YearMonth']], rotation=45, ha='right', fontsize=9)
ax.set_title('Monthly Income vs Spending (Main Account)')
ax.set_ylabel('Amount ($)')
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax.legend()
fig.tight_layout()
CHART_MONTHLY = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# CHART 7 — Savings simulation
# ═══════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# Left: cumulative savings curves over time
ax = axes[0]
colors_sim = ['#3498db','#2ecc71','#e74c3c']
for frac, col in zip([0.10, 0.20, 0.30], colors_sim):
    running = []
    dates_sim = []
    bal = 0.0
    for _, row_s in income_events.iterrows():
        deposit = row_s['amount'] * frac
        bal = bal * (1 + ANNUAL_RATE * 1/12)  # approx monthly compounding for chart
        bal += deposit
        running.append(bal)
        dates_sim.append(row_s['date'])
    ax.plot(dates_sim, running, color=col, linewidth=2, label=f'Save {int(frac*100)}%')
ax.set_title('Hypothetical Savings Account — What Would It Hold Today?')
ax.set_ylabel('Savings balance ($)')
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
fig.autofmt_xdate(rotation=30)
ax.legend()

# Right: bar chart of final values
ax2 = axes[1]
fracs = [0.10, 0.20, 0.30]
finals = [savings_results[f] for f in fracs]
contribs = []
for f in fracs:
    c = sum(r['amount'] * f for _, r in income_events.iterrows())
    contribs.append(c)
interest = [finals[i] - contribs[i] for i in range(3)]
x_bar = np.arange(3)
b1 = ax2.bar(x_bar, contribs, color='#3498db', label='Cash contributed', edgecolor='white')
b2 = ax2.bar(x_bar, interest, bottom=contribs, color='#2ecc71', label='Interest earned', edgecolor='white')
for i, (tot, c) in enumerate(zip(finals, contribs)):
    ax2.text(i, tot + 15, f'${tot:,.0f}', ha='center', fontsize=12, fontweight='bold', color='#222')
ax2.set_xticks(x_bar)
ax2.set_xticklabels(['Save 10%', 'Save 20%', 'Save 30%'], fontsize=12)
ax2.set_title('Balance Today by Savings Rate\n(5% annual return, compound)')
ax2.set_ylabel('Amount ($)')
ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))
ax2.legend()
fig.tight_layout()
CHART_SAVINGS = fig_to_b64(fig)

# ═══════════════════════════════════════════════════════════════════════════
# TOP MERCHANT TABLE (for report)
# ═══════════════════════════════════════════════════════════════════════════
spend_df['Payee_clean'] = spend_df['Payee'].str.strip()
merch_tbl = (spend_df.groupby(['Payee_clean','Category'])
             .agg(total=('Amount', lambda x: x.abs().sum()),
                  visits=('Amount','count'))
             .reset_index()
             .sort_values('total', ascending=False)
             .head(20))

def merch_table_html(df_tbl):
    rows = ''
    for _, r in df_tbl.iterrows():
        avg = r['total'] / r['visits']
        c = cat_colors_map.get(r['Category'], '#95a5a6')
        rows += (f'<tr>'
                 f'<td>{r["Payee_clean"]}</td>'
                 f'<td><span class="cat-badge" style="background:{c}">{r["Category"]}</span></td>'
                 f'<td class="num">${r["total"]:,.2f}</td>'
                 f'<td class="num">{r["visits"]}</td>'
                 f'<td class="num">${avg:.2f}</td>'
                 f'</tr>')
    return f'''<table class="data-table">
      <thead><tr>
        <th>Merchant</th><th>Category</th>
        <th>Total spent</th><th>Visits</th><th>Avg/visit</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''

MERCH_TABLE = merch_table_html(merch_tbl)

# ═══════════════════════════════════════════════════════════════════════════
# HTML REPORT
# ═══════════════════════════════════════════════════════════════════════════
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{PERSON_NAME}'s Spending Report — May 2024 to May 2026</title>
<style>
  /* ── Reset & base ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13.5px;
    line-height: 1.6;
    color: #222;
    background: #fff;
    max-width: 960px;
    margin: 0 auto;
    padding: 32px 28px 60px;
  }}
  h1 {{ font-size: 2em; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }}
  h2 {{ font-size: 1.35em; font-weight: 700; color: #1a1a2e; margin: 40px 0 10px;
        border-bottom: 3px solid #e74c3c; padding-bottom: 6px; }}
  h3 {{ font-size: 1.1em; font-weight: 600; color: #2c3e50; margin: 20px 0 6px; }}
  p  {{ margin-bottom: 10px; }}
  .subtitle {{ color: #555; font-size: 1em; margin-bottom: 28px; }}

  /* ── Key stats bar ── */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 28px 0 36px;
  }}
  .stat-card {{
    background: #1a1a2e;
    color: #fff;
    border-radius: 10px;
    padding: 18px 14px;
    text-align: center;
  }}
  .stat-card .value {{
    font-size: 2em;
    font-weight: 700;
    color: #e74c3c;
    display: block;
    line-height: 1.1;
  }}
  .stat-card .label {{
    font-size: 0.82em;
    color: #aaa;
    margin-top: 5px;
    display: block;
  }}
  .stat-card.green  .value {{ color: #2ecc71; }}
  .stat-card.orange .value {{ color: #f39c12; }}
  .stat-card.purple .value {{ color: #9b59b6; }}

  /* ── Alert box ── */
  .alert {{
    border-left: 5px solid #e74c3c;
    background: #fff5f5;
    padding: 14px 18px;
    margin: 18px 0 22px;
    border-radius: 0 6px 6px 0;
  }}
  .alert strong {{ color: #c0392b; }}
  .insight {{
    border-left: 5px solid #3498db;
    background: #f0f8ff;
    padding: 14px 18px;
    margin: 18px 0 22px;
    border-radius: 0 6px 6px 0;
  }}
  .insight strong {{ color: #1a5276; }}
  .good {{
    border-left: 5px solid #2ecc71;
    background: #f0fff4;
    padding: 14px 18px;
    margin: 18px 0 22px;
    border-radius: 0 6px 6px 0;
  }}
  .good strong {{ color: #1e8449; }}

  /* ── Charts ── */
  .chart-wrap {{
    margin: 22px 0 8px;
    border: 1px solid #eee;
    border-radius: 8px;
    overflow: hidden;
    background: #fff;
  }}
  .chart-caption {{
    font-size: 0.88em;
    color: #555;
    padding: 10px 14px 14px;
    background: #fafafa;
    border-top: 1px solid #eee;
  }}
  .chart-caption strong {{ color: #222; }}

  /* ── Tables ── */
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92em;
    margin: 16px 0;
  }}
  .data-table th {{
    background: #1a1a2e;
    color: #eee;
    padding: 9px 12px;
    text-align: left;
    font-weight: 600;
  }}
  .data-table td {{
    padding: 8px 12px;
    border-bottom: 1px solid #eee;
  }}
  .data-table tr:nth-child(even) td {{ background: #f8f9fa; }}
  .data-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .cat-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.82em;
    color: #fff;
    font-weight: 600;
    white-space: nowrap;
  }}

  /* ── Savings table ── */
  .savings-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 1em;
    margin: 16px 0;
  }}
  .savings-table th {{
    background: #1a1a2e;
    color: #eee;
    padding: 10px 14px;
    text-align: center;
  }}
  .savings-table td {{
    padding: 12px 14px;
    border-bottom: 1px solid #eee;
    text-align: center;
  }}
  .savings-table .highlight-row td {{
    font-weight: 700;
    font-size: 1.1em;
    background: #fffbea;
  }}
  .savings-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

  /* ── Conclusion ── */
  .conclusion {{
    background: #1a1a2e;
    color: #eee;
    padding: 28px 32px;
    border-radius: 10px;
    margin-top: 44px;
  }}
  .conclusion h2 {{
    color: #fff;
    border-bottom-color: #e74c3c;
    margin-top: 0;
  }}
  .conclusion ul {{
    margin: 12px 0 0 20px;
    line-height: 2;
  }}
  .conclusion li {{ margin-bottom: 4px; }}
  .conclusion .red   {{ color: #e74c3c; font-weight: 700; }}
  .conclusion .green {{ color: #2ecc71; font-weight: 700; }}
  .conclusion .gold  {{ color: #f39c12; font-weight: 700; }}

  /* ── Footer ── */
  .footer {{
    margin-top: 48px;
    padding-top: 14px;
    border-top: 1px solid #ddd;
    font-size: 0.82em;
    color: #888;
    text-align: center;
  }}

  /* ── Print ── */
  @media print {{
    body {{ max-width: 100%; padding: 10mm 15mm; font-size: 12px; }}
    h2   {{ margin-top: 24px; }}
    .stats-grid {{ grid-template-columns: repeat(4, 1fr); }}
    .chart-wrap  {{ page-break-inside: avoid; }}
    .conclusion  {{ page-break-inside: avoid; }}
    .no-print    {{ display: none; }}

    /* stat cards: dark bg → white with coloured border + dark text */
    .stat-card {{
      background: #fff !important;
      color: #222 !important;
      border: 2px solid #ccc;
      border-radius: 10px;
    }}
    .stat-card .value  {{ color: #c0392b !important; }}
    .stat-card .label  {{ color: #444 !important; }}
    .stat-card.green  .value {{ color: #1e8449 !important; }}
    .stat-card.orange .value {{ color: #b7770d !important; }}
    .stat-card.purple .value {{ color: #6c3483 !important; }}

    /* coloured left-border boxes: keep border, lighten bg */
    .alert   {{ background: #fff !important; border-left: 4px solid #e74c3c; }}
    .insight {{ background: #fff !important; border-left: 4px solid #2980b9; }}
    .good    {{ background: #fff !important; border-left: 4px solid #27ae60; }}
    .alert strong   {{ color: #c0392b !important; }}
    .insight strong {{ color: #1a5276 !important; }}
    .good strong    {{ color: #1e8449 !important; }}

    /* chart wrap: keep border, drop shadow bg */
    .chart-wrap    {{ border: 1px solid #ccc; background: #fff !important; }}
    .chart-caption {{ background: #fff !important; border-top: 1px solid #ddd; color: #444 !important; }}

    /* tables: dark header → light grey */
    .data-table th, .savings-table th {{
      background: #f0f0f0 !important;
      color: #222 !important;
      border-bottom: 2px solid #999;
    }}
    .data-table tr:nth-child(even) td {{ background: #f8f8f8 !important; }}
    .savings-table .highlight-row td  {{ background: #fffbea !important; }}

    /* conclusion box: dark bg → white with strong border */
    .conclusion {{
      background: #fff !important;
      color: #222 !important;
      border: 2px solid #333;
      border-radius: 10px;
    }}
    .conclusion h2 {{ color: #1a1a2e !important; }}
    .conclusion .red   {{ color: #c0392b !important; }}
    .conclusion .green {{ color: #1e8449 !important; }}
    .conclusion .gold  {{ color: #b7770d !important; }}
    .conclusion p      {{ color: #444 !important; }}

    /* cat badges: keep colour but ensure text readable */
    .cat-badge {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>

<h1>{PERSON_NAME}'s Spending Report</h1>
<p class="subtitle">Main account analysis &nbsp;·&nbsp; May 2024 – May 2026 &nbsp;·&nbsp;
Two full years of transactions &nbsp;·&nbsp; Reimbursed pass-throughs excluded</p>

<!-- KEY STATS -->
<div class="stats-grid">
  <div class="stat-card">
    <span class="value">${total_real_income:,.0f}</span>
    <span class="label">Real income received<br>(no double-counting)</span>
  </div>
  <div class="stat-card">
    <span class="value">${impulse_total/24:.0f}</span>
    <span class="label">average per month on impulse spending</span>
  </div>
  <div class="stat-card orange">
    <span class="value">{median_days:.0f} days</span>
    <span class="label">median time from money arriving to account empty</span>
  </div>
  <div class="stat-card green">
    <span class="value">${savings_results[0.20]:,.0f}</span>
    <span class="label">what a 20% savings habit would hold today</span>
  </div>
</div>

<div class="alert">
<strong>The short version:</strong> Over two years, ${food_total:,.0f} went on food and drinks,
${gaming_total:,.0f} on gaming and subscriptions — together that's
{100*(food_total+gaming_total)/total_real_income:.0f}% of every dollar received. When money arrives,
it's typically gone within {median_days:.0f} days. Almost nothing was saved. This is not about
big mistakes — it's the compounding effect of dozens of small, unconsidered decisions every month.
</div>

<!-- SECTION 1 -->
<h2>1 · Where Does the Money Go?</h2>
<p>Every transaction categorised. Reimbursed pass-throughs are
<em>excluded</em> — everything here is genuinely the account holder's own spending decisions.</p>

<div class="chart-wrap">
  {img_tag(CHART_CATS, 'Spending by category')}
  <div class="chart-caption">
    <strong>Left:</strong> Total two-year spend per category.
    <strong>Right:</strong> The same data as proportions — food-related categories alone account
    for {100*food_total/total_real_spend:.0f}% of everything spent.
    Add gaming and subscriptions and it's {100*(food_total+gaming_total)/total_real_spend:.0f}%.
    There is no large discretionary category that could be cut — the spending is distributed
    across hundreds of individually small transactions.
  </div>
</div>

<h3>Top 15 merchants by total spend</h3>
{MERCH_TABLE}

<div class="alert">
<strong>Notice:</strong> Supermarket and convenience store visits are not weekly grocery shops —
they are snack runs averaging $3–6 each, happening multiple times per week.
There is no single big purchase to point to. The damage is done in increments of $4.
</div>

<!-- SECTION 2 -->
<h2 style="page-break-before:always;">2 · Impulse Spending in Detail</h2>
<p>Food, fast food, cafés, and gaming are the four categories driven entirely by in-the-moment decisions.
Here is what those look like month by month, and which specific places are the biggest contributors.</p>

<div class="chart-wrap">
  {img_tag(CHART_IMPULSE, 'Monthly impulse spending and top merchants')}
  <div class="chart-caption">
    <strong>Left:</strong> Each coloured segment is a category; the bars stack to the total impulse spend
    that month. The dashed line is the monthly average (${impulse_total/24:.0f}).
    There is no trend downward — if anything spending increases over the period.<br>
    <strong>Right:</strong> The top 12 impulse merchants ranked by total two-year damage.
  </div>
</div>

<div class="stats-grid" style="grid-template-columns:repeat(4,1fr);margin:24px 0;">
  <div class="stat-card">
    <span class="value">${impulse_total:,.0f}</span>
    <span class="label">Total impulse spend (24 months)</span>
  </div>
  <div class="stat-card orange">
    <span class="value">${impulse_total/24:.0f}</span>
    <span class="label">Per month, on average</span>
  </div>
  <div class="stat-card purple">
    <span class="value">${gaming_total:,.0f}</span>
    <span class="label">Gaming &amp; subscriptions total</span>
  </div>
  <div class="stat-card">
    <span class="value">{100*impulse_total/total_real_income:.0f}%</span>
    <span class="label">of all real income, on impulse alone</span>
  </div>
</div>

<!-- SECTION 3 -->
<h2>3 · Monthly Income vs Spending</h2>
<p>For savings to accumulate, the green bars need to be consistently taller than the red.
The rolling average line shows whether spending is increasing or decreasing over time.</p>

<div class="chart-wrap">
  {img_tag(CHART_MONTHLY, 'Monthly income vs spending')}
  <div class="chart-caption">
    <strong>How to read this:</strong> Green = income that month, red = spending. When red is taller, the
    account shrank. The dark red line is the 3-month rolling average of spending — it shows the underlying
    trend without monthly noise. Notice how income and spending track almost perfectly: money arrives,
    money leaves. The account almost never builds a buffer.
  </div>
</div>

<!-- SECTION 4 -->
<h2 style="page-break-before:always;">4 · What Could Have Been — The Savings Simulation</h2>
<p>Assume {PERSON_NAME} had automatically transferred a fixed percentage of every payment into a separate
investment account the moment it arrived — <em>before</em> spending anything — earning 5% per year
compounding. Here is what that account would hold today.</p>

<div class="chart-wrap">
  {img_tag(CHART_SAVINGS, 'Savings simulation')}
  <div class="chart-caption">
    <strong>Left:</strong> The hypothetical savings balance growing over time for each savings rate.
    The curve starts low and accelerates — this is compounding. The earlier the saving starts, the
    steeper the curve.<br>
    <strong>Right:</strong> The final balance today, split between cash contributed (blue) and
    interest earned (green). The green portion is free money — it existed only because the cash
    was kept invested instead of spent.
  </div>
</div>

<table class="savings-table">
  <thead>
    <tr>
      <th>Save each payment</th>
      <th>Cash put aside</th>
      <th>Interest earned</th>
      <th>Balance today</th>
      <th>Monthly cost (avg)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>10%</td>
      <td>${sum(r['amount']*0.10 for _,r in income_events.iterrows()):,.0f}</td>
      <td>${savings_results[0.10] - sum(r['amount']*0.10 for _,r in income_events.iterrows()):,.0f}</td>
      <td><strong>${savings_results[0.10]:,.0f}</strong></td>
      <td>${total_real_income/24*0.10:.0f} / month</td>
    </tr>
    <tr class="highlight-row">
      <td>20%</td>
      <td>${sum(r['amount']*0.20 for _,r in income_events.iterrows()):,.0f}</td>
      <td>${savings_results[0.20] - sum(r['amount']*0.20 for _,r in income_events.iterrows()):,.0f}</td>
      <td><strong>${savings_results[0.20]:,.0f}</strong></td>
      <td>${total_real_income/24*0.20:.0f} / month</td>
    </tr>
    <tr>
      <td>30%</td>
      <td>${sum(r['amount']*0.30 for _,r in income_events.iterrows()):,.0f}</td>
      <td>${savings_results[0.30] - sum(r['amount']*0.30 for _,r in income_events.iterrows()):,.0f}</td>
      <td><strong>${savings_results[0.30]:,.0f}</strong></td>
      <td>${total_real_income/24*0.30:.0f} / month</td>
    </tr>
  </tbody>
</table>

<div class="good">
<strong>Deliberate saving periods show the discipline exists.</strong> During the high-balance periods
shown in the balance chart below, the account holder demonstrably held back spending and built up a
balance with intent. The habit is not absent — it just hasn't been applied by default. Automating a
transfer the moment money arrives removes the decision entirely.
</div>

<!-- SECTION 5 -->
<h2>5 · The Big Picture — Two Years of Balance</h2>
<p>Every green dot is a day money arrived. Every spike immediately drops back toward zero (the red dashed line).
The orange-shaded zones are periods where the balance stayed elevated for more than a week — typically
a larger windfall (birthday cash, a bigger payment) that just took longer to spend rather than a conscious
savings decision. Everything outside the orange zones is the default behaviour.</p>

<div class="chart-wrap">
  {img_tag(CHART_BALANCE, 'Running balance over time')}
  <div class="chart-caption">
    <strong>How to read this:</strong> The y-axis is the end-of-day account balance in dollars.
    Each time the line drops to the red dashed line, the account is effectively empty.
    Count the number of times that happens — that's not a fluke, it's the default pattern.
    The orange zones are windfall periods that took more than a week to spend — excluded from
    the drain-speed statistics so they don't skew the typical picture.
  </div>
</div>

<!-- BROKE DAYS CHART -->
<div class="chart-wrap" style="margin-top:20px;">
  {img_tag(CHART_BROKE_DAYS, 'Broke days timeline and monthly count')}
  <div class="chart-caption">
    <strong>Top:</strong> The full two-year balance, with every day where the account held ≤$1
    highlighted in red. <strong>Bottom:</strong> How many of those days fell in each calendar month —
    the number above each bar is the count. A month with 10+ red days means the account holder was
    functionally broke for a third of the month. The dashed line is the two-year monthly average.
    <strong>Total broke days: {broke_days_total} out of {len(daily)} ({100*broke_days_total/len(daily):.0f}%
    of all days analysed).</strong>
  </div>
</div>

<!-- SECTION 6 -->
<h2>6 · How Fast Does It Drain?</h2>
<p>For each normal money-in event, how long until the balance hit $1 or less?</p>

<div class="chart-wrap">
  {img_tag(CHART_BROKE, 'Days to reach $1')}
  <div class="chart-caption">
    <strong>Left chart:</strong> Count of episodes that drained in exactly X days.
    The gap at day 3 is not a plotting error — it genuinely never happened to take exactly 3 days.
    Days 0–2 and then 4–7 are where most episodes land.<br>
    <strong>Right chart:</strong> The cumulative view — by day 2, more than 10% of <em>all</em> normal
    money-in events have already gone to zero. By day 5, that's around 15%.
    The dotted lines mark where 50% and 75% of the drained episodes fall.
  </div>
</div>

<div class="chart-wrap" style="margin-top:20px;">
  {img_tag(CHART_DRAIN, 'Average balance decay')}
  <div class="chart-caption">
    <strong>How to read this:</strong> Every "went broke" episode is aligned to Day 0 (money arrived = 100%)
    and overlaid. The <strong>blue median line</strong> is the most reliable measure — the dashed red mean
    is shown for reference but gets distorted over time because episodes that drain fast hit zero and
    drop out of the sample, leaving only the slower ones, which pulls the mean back up. That's why both
    lines appear to tick upward around day 3: it's not a recovery, it's the fast-spenders having already
    left. The <em>n=</em> counts along the bottom show how quickly the sample shrinks.
    The median tells the honest story: half the money is gone within 2 days.
  </div>
</div>

<div class="insight">
<strong>The math:</strong> Of the normal money-in events, {len(broke_episodes)} ({pct_went_broke:.0f}%) fully
drained to ≤$1 before the <em>next</em> payment arrived — no 7-day cut-off, just "did it hit zero
before more money came in?" Of those {len(broke_episodes)}, the median time from payment to broke was
<strong>{median_days:.0f} days</strong>. The remaining {len(normal) - len(broke_episodes)} episodes ({100 - pct_went_broke:.0f}%)
didn't technically hit zero, but mostly because new money arrived first — not because spending
stopped. The account almost never builds a buffer voluntarily.
</div>

<!-- CONCLUSION -->
<div class="conclusion">
  <h2>Summary — The Numbers Don't Lie</h2>
  <ul>
    <li><span class="red">${total_real_income:,.0f}</span> in real income arrived over 2 years (~${total_real_income/24:.0f}/month average).</li>
    <li><span class="red">{pct_went_broke:.0f}%</span> of money-in events drained fully to ≤$1 before the next payment arrived — median time to broke: <span class="red">{median_days:.0f} days</span>. The rest ran out of time, not spending.</li>
    <li><span class="red">${food_total:,.0f}</span> spent on food and drinks across 4 categories — <span class="red">{100*food_total/total_real_income:.0f}%</span> of all real income.</li>
    <li><span class="red">${gaming_total:,.0f}</span> on gaming and subscriptions — individually small, collectively significant.</li>
    <li><span class="red">${impulse_total:,.0f}</span> total impulse spend = <span class="red">{100*impulse_total/total_real_income:.0f}%</span> of every dollar received.</li>
    <li>Saving 20% automatically from day one would have built <span class="green">${savings_results[0.20]:,.0f}</span> by now.</li>
    <li><span class="gold">Deliberate saving periods show the discipline exists</span> — it just hasn't been applied as a default rule.</li>
  </ul>
  <p style="margin-top:18px;color:#ccc;font-size:0.92em;">
  The pattern is not about large mistakes or bad luck. It is the result of hundreds of individually
  reasonable-feeling decisions that collectively consume nearly every dollar received. The fix isn't
  willpower — it's a system: automate a transfer to a separate account the moment any payment arrives,
  before the account balance is visible. What you don't see, you don't spend.
  </p>
</div>

<div class="footer">
  Generated {TODAY_SIM.strftime('%d %B %Y')} &nbsp;·&nbsp;
  Data: May 2024 – May 2026 &nbsp;·&nbsp;
  Reimbursed pass-throughs excluded from all analysis
</div>

</body>
</html>"""

outfile = f'{PERSON_NAME.lower()}_spending_report.html'
with open(outfile, 'w') as f:
    f.write(html)

print(f"Report written to {outfile}")
print(f"File size: {len(html)/1024:.0f} KB")
