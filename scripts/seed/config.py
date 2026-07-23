from decimal import Decimal

PROFILES = {
    "small": {"customers": 100},
    "medium": {"customers": 10_000},
    "large": {"customers": 100_000},
}

DEFAULT_PROFILE = "medium"

# Fixed seed so a given customer count always produces the same dataset.
RANDOM_SEED = 42

# --- Branch / employee scaling -------------------------------------------
# One branch per N customers, with a floor so small datasets still get a
# believable minimum branch network.
BRANCH_DENSITY = 1500
MIN_BRANCHES = 2
EMPLOYEES_PER_BRANCH_RANGE = (4, 10)

# --- Accounts --------------------------------------------------------------
# Most customers own exactly one account; a minority own more.
ACCOUNTS_PER_CUSTOMER_WEIGHTS = {1: 0.80, 2: 0.15, 3: 0.05}

# --- Organic transaction activity (deposits/withdrawals) --------------------
TRANSACTIONS_PER_ACCOUNT_RANGE = (3, 15)
OPENING_DEPOSIT_RANGE = (100.00, 5000.00)
DEPOSIT_AMOUNT_RANGE = (20.00, 3000.00)
WITHDRAWAL_FRACTION_RANGE = (0.05, 0.35)  # fraction of current balance

# --- Transfers ---------------------------------------------------------------
TRANSFER_PARTICIPATION_RATE = 0.40  # fraction of accounts that send >=1 transfer
TRANSFERS_PER_SENDER_RANGE = (1, 5)
TRANSFER_FRACTION_RANGE = (0.05, 0.30)  # fraction of sender's current balance
LARGE_TRANSFER_THRESHOLD = Decimal("10000.00")

# --- Channel simulation --------------------------------------------------------
EMPLOYEE_ASSISTED_RATE = 0.30  # fraction of activity with performed_by_employee_id set

# --- Timing ---------------------------------------------------------------------
HISTORY_MONTHS = 12

# --- Bulk-load batching ------------------------------------------------------------
COPY_BATCH_SIZE = 5000
