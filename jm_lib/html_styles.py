"""HTML 공통 head 유틸리티
4개 HTML 생성 모듈(options/portfolio/technical/alpha_hunter)에서 중복되는
DOCTYPE 선언 · meta 태그 · CSS 리셋 · CDN 링크를 단일 소스로 관리한다.

사용법:
    from jm_lib.html_styles import html_head
    return html_head('페이지 제목', css=MODULE_CSS, chartjs=True) + f"<body>...</body></html>"
"""

# ═══ CDN 상수 ═══

CHARTJS_CDN = (
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0'
    '/dist/chart.umd.min.js"></script>'
)

HTML2CANVAS_CDN = (
    '<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1'
    '/dist/html2canvas.min.js"></script>'
)

# ═══ 기본 CSS 리셋 ═══

BASE_RESET = '*{box-sizing:border-box;margin:0;padding:0}'


# ═══ head 생성 함수 ═══

def html_head(title: str,
              css: str = '',
              chartjs: bool = False,
              html2canvas: bool = False,
              extra_scripts: str = '') -> str:
    """공통 HTML <head> 섹션 생성.

    Args:
        title:          <title> 태그 텍스트
        css:            모듈 전용 스타일 문자열 (BASE_RESET은 자동 포함)
        chartjs:        chart.js@4.4.0 CDN 포함 여부
        html2canvas:    html2canvas@1.4.1 CDN 포함 여부
        extra_scripts:  추가 <script> 태그 문자열

    Returns:
        ``<!DOCTYPE html>`` 부터 ``</head>`` 까지의 완성된 문자열
    """
    cdn_lines = ''
    if chartjs:
        cdn_lines += f'\n{CHARTJS_CDN}'
    if html2canvas:
        cdn_lines += f'\n{HTML2CANVAS_CDN}'
    if extra_scripts:
        cdn_lines += f'\n{extra_scripts}'

    style_content = BASE_RESET
    if css.strip():
        style_content += '\n' + css.strip()

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="ko">\n'
        f'<head>\n'
        f'<meta charset="UTF-8">\n'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'{cdn_lines}\n'
        f'<title>{title}</title>\n'
        f'<style>\n'
        f'{style_content}\n'
        f'</style>\n'
        f'</head>'
    )


__all__ = [
    'html_head',
    'BASE_RESET',
    'CHARTJS_CDN',
    'HTML2CANVAS_CDN',
]
