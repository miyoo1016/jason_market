import yfinance as yf

symbols = {
    'Bitcoin': 'BTC-USD',
    'Gold': 'GC=F',
    'Google': 'GOOGL',
    'Nasdaq': 'QQQM',
    'S&P500': 'SPY',
}

print("\n" + "="*80)
print("현재 시세".center(80))
print("="*80 + "\n")

for name, ticker in symbols.items():
    try:
        df = yf.download(ticker, period='1d', progress=False)
        current = float(df['Close'].iloc[-1].item())
        print(f"{name:20}: ${current:>12,.2f}")
    except Exception as e:
        print(f"❌ {name}: {str(e)}")

print("="*80 + "\n")
