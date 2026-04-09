import pandas as pd
import os

XLSX_PATH = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-miyoo1016@gmail.com"
    "/내 드라이브/PF/자산 계산기(클로드).xlsx"
)
SHEET_NAME = "📊 자산 계산기"

if os.path.exists(XLSX_PATH):
    try:
        df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME, header=None)
        # 상단 20행, 좌측 15열 정도를 덤프해서 어디에 환율이나 추가 정보가 있는지 확인
        print("--- Excel Top-Left Area (15x15) ---")
        sub_df = df.iloc[:20, :15]
        print(sub_df.to_string())
        
        print("\n--- Searching for '환율' or '원화' in values ---")
        for r in range(min(20, len(df))):
            for c in range(min(20, len(df.columns))):
                val = str(df.iloc[r, c])
                if '환율' in val or '원화' in val or '투자' in val:
                    print(f"[{r}, {c}]: {val}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("File not found.")
