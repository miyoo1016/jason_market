import openpyxl
import os
import platform

_sys = platform.system()
if _sys == "Windows":
    XLSX_PATH = r"G:\내 드라이브\PF\자산 계산기(클로드).xlsx"
elif _sys == "Darwin":  # macOS
    XLSX_PATH = os.path.expanduser(
        "~/Library/CloudStorage/GoogleDrive-miyoo1016@gmail.com"
        "/내 드라이브/PF/자산 계산기(클로드).xlsx"
    )
else:
    XLSX_PATH = ""

SHEET_NAME = "📊 자산 계산기"

def modify_excel():
    if not os.path.exists(XLSX_PATH):
        print(f"Error: File not found at {XLSX_PATH}")
        return False
    
    try:
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb[SHEET_NAME]
        
        # H열(8번째 컬럼)의 첫 번째 행에 제목 추가
        header_cell = ws.cell(row=1, column=8)
        if header_cell.value != "매수원가(₩)":
            header_cell.value = "매수원가(₩)"
            # 약간의 스타일링 (선택 사항 - 굵게)
            header_cell.font = openpyxl.styles.Font(bold=True)
            wb.save(XLSX_PATH)
            print("Successfully added '매수원가(₩)' header to Column H.")
        else:
            print("Header '매수원가(₩)' already exists in Column H.")
        
        return True
    except Exception as e:
        print(f"Error modifying Excel: {e}")
        return False

if __name__ == "__main__":
    modify_excel()
