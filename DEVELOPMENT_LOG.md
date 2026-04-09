# Development Log - Jason Market Portfolio Tracker

## Last Updated: 2026-04-08 (23:50 KST)

## 📌 Project Overview & System Status
Currently, the system is a high-precision, real-time portfolio tracker that integrates with a Google Drive-synced Excel file (`자산 계산기(클로드).xlsx`). It handles both stock prices and FX fluctuations to provide a comprehensive view of KRW assets.

## ✅ Key Achievements (Context for switching machines)

### 1. High-Precision Cost Tracking (Column L)
- **Logic**: The script now uses **Column L (매입환율)** in the Excel sheet for accurate cost calculation.
- **Intelligent Recognition**: 
    - If a value in Column L is `< 10,000`, it is treated as a **Purchase FX Rate** (e.g., 1,463.01). The script multiplies this by `Qty * Avg Price` to get the cost.
    - If a value is `>= 10,000`, it is treated as the **Total KRW Cost** (e.g., 55,000,000).
- **Automation**: `xlsx_sync.py` automatically adds this header to L9, sets its width to 20, and matches its style to the rest of the table.

### 2. Real-Time FX and Excel Sync (Cell O14)
- **Automatic Write-back**: `portfolio_tracker.py` now fetches the real-time `USDKRW=X` rate and **writes it back to cell O14** in the Excel file.
- **Benefit**: This keeps the Excel file's internal formulas (using O14) perfectly in sync with the live market and our dashboard.
- **Pricing**: We use Yahoo Finance for real-time prices, even when Korean brokers (like Samsung) show temporary inflated/frozen exchange rates.

### 3. PnL Logic Refinement
- **1-day PnL**: Includes both Price move and FX move: `(Price_today * FX_today) - (Price_yesterday * FX_yesterday)`.
- **FX PnL**: Isolated gain/loss from currency movement relative to the base rate in Column L.

### 4. Real-time FX Accuracy Fix (yfinance)
- **Problem**: `history()` was returning a delayed "Close" price (1507 KRW), causing incorrect valuation.
- **Fix**: Switched to `fast_info['last_price']`, which provides the actual current rate (~1476 KRW).
- **Consistency**: Applied this fix to both `portfolio_tracker.py` and `xlsx_sync.py`.

### 5. Exact Percentage Change Calculation
- **Fix**: `view_prices.py` now calculates percentage changes (등락률) using the actual historical daily close instead of potentially unreliable real-time fields. 
- **Result**: Verified accurate gains for QQQM (+2.78%) and GOOGL (+3.62%).

### 6. Excel Corruption Prevention ("Safe Save")
- **Mechanism**: Implemented atomic saving in `xlsx_sync.py`. It saves to a `.tmp` file first and replaces the original only if successful.
- **Environment**: Fixed a Pandas 3.0.2 compatibility error by explicitly setting `engine='openpyxl'`.
- **Recovery**: Restored the corrupted 1.5KB file from the 21KB original backup.

## 🚀 To-Do / Next Steps
- Continue refortifying calculations as market opens tomorrow.
- Finalize any additional UI/UX tweaks for the news dashboard if needed.

---
**When resuming work on a new machine (Mac/Windows):**
Just tell Antigravity, "Continue today's work context" and it will read this log to understand the full system state.
