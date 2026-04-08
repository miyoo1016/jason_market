# Development Log - Jason Market Portfolio Tracker

## Last Updated: 2026-04-08 (19:10 KST)

## 📌 Project Overview & System Status
Currently, the system is a high-precision, real-time portfolio tracker that integrates with a Google Drive-synced Excel file (`자산 계산기(클로드).xlsx`). It handles both stock prices and FX fluctuations to provide a comprehensive view of KRW assets.

## ✅ Key Achievements (Context for switching machines)

### 1. High-Precision Cost Tracking (Column L)
- **Logic**: The script now uses **Column L (매수원가(₩))** in the Excel sheet for accurate cost calculation.
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

## 🚀 To-Do / Next Steps
- Monitor the accuracy compared to brokers during market opening.
- Any further refinements to the HTML dashboard styling.

---
**When resuming work on a new machine (Mac/Windows):**
Just tell Antigravity, "Continue today's work context" and it will read this log to understand the full system state.
