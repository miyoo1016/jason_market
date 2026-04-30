"""Alpha Hunter — HTML 생성 및 렌더링
대시보드 및 카드 HTML 생성"""

import os
import json
from datetime import datetime

from jm_lib.html_styles import html_head
from alpha_hunter_base import SIGNALS_DIR, SEED_LIST, HTML_OUT
from alpha_hunter_md import excerpt_md, urlhost

SOURCE_COLORS = {
    'seed':    ('#2e7d32', '#edf7ee', '#2e7d32'),
    'reddit':  ('#c94b2b', '#fff1ee', '#c94b2b'),
}
SOURCE_LABELS_MAP = {
    'seed':   '시드 피드',
    'reddit': 'Reddit',
}


def build_cards_html(posts: list) -> str:
    """포스트 카드 HTML 생성"""
    if not posts:
        return '<div class="empty">수집된 글이 없습니다. seed_list.json을 확인하거나 잠시 후 재실행하세요.</div>'

    parts = []
    for p in posts:
        src    = p['source']
        sc     = SOURCE_COLORS.get(src, ('#555', '#f5f5f5', '#ccc'))
        slabel = SOURCE_LABELS_MAP.get(src, src)
        raw_ex = p.get('excerpt', '')
        disp_ex = excerpt_md(raw_ex)

        excerpt_html = ''
        if disp_ex:
            ex = disp_ex.replace('<', '&lt;').replace('>', '&gt;')
            excerpt_html = f'<p class="excerpt">{ex}</p>'

        parts.append(f'''
<div class="card" data-source="{src}">
  <div class="card-header">
    <span class="badge" style="color:{sc[0]};background:{sc[1]};border-color:{sc[2]}">{slabel}</span>
    <span class="card-label">{p["label"].replace("<","&lt;").replace(">","&gt;")}</span>
    <span class="card-date">{p["date"]}</span>
  </div>
  <a class="card-title" href="{p["url"]}" target="_blank" rel="noopener">
    {p["title"].replace("<","&lt;").replace(">","&gt;")}
  </a>
  <div class="card-meta">
    <span>✍ {p["author"].replace("<","&lt;")}</span>
  </div>
  {excerpt_html}
  <div class="card-footer">
    <a href="{p["url"]}" target="_blank" rel="noopener" class="link-btn">원문 열기 →</a>
  </div>
</div>''')

    return '\n'.join(parts)


def build_macro_html(macro_data: dict) -> str:
    """Macro & Flow Dashboard HTML 섹션 생성"""
    if not macro_data:
        return ''

    fg        = macro_data.get('fg')
    vix       = macro_data.get('vix')
    cot       = macro_data.get('cot')
    headlines = macro_data.get('headlines', [])

    # ── Fear & Greed 바 ─────────────────────────────────────
    if fg:
        score   = fg['score']
        pct     = score  # 0~100 → %
        # 색상 구간
        if score <= 25:
            bar_color = '#c62828'   # 극도 공포 (붉은)
        elif score <= 45:
            bar_color = '#e65100'   # 공포 (주황)
        elif score <= 55:
            bar_color = '#7b6f3a'   # 중립 (올리브)
        elif score <= 75:
            bar_color = '#00838f'   # 탐욕 (teal)
        else:
            bar_color = '#1a5c3a'   # 극도 탐욕 (녹색)

        prev_html = ''
        if fg.get('prev1w'):
            delta = round(score - fg['prev1w'], 1)
            sign  = '+' if delta >= 0 else ''
            prev_html = f'<span class="mcd-prev">1주전 {fg["prev1w"]} ({sign}{delta})</span>'

        fg_html = f'''
<div class="mcd-card">
  <div class="mcd-card-title">📊 CNN Fear &amp; Greed</div>
  <div class="mcd-score" style="color:{bar_color}">{score}</div>
  <div class="mcd-label" style="color:{bar_color}">{fg["label"]}</div>
  <div class="mcd-bar-wrap">
    <div class="mcd-bar-bg">
      <div class="mcd-bar-fill" style="width:{pct}%;background:{bar_color}"></div>
    </div>
    <div class="mcd-bar-range"><span>0 극도공포</span><span>100 극도탐욕</span></div>
  </div>
  {prev_html}
</div>'''
    else:
        fg_html = '<div class="mcd-card"><div class="mcd-card-title">📊 CNN Fear &amp; Greed</div><div class="mcd-na">조회 실패</div></div>'

    # ── VIX ─────────────────────────────────────────────────
    if vix:
        sign     = '+' if vix['change'] >= 0 else ''
        vix_col  = '#c62828' if vix['change'] > 2 else ('#e65100' if vix['change'] > 0 else '#00838f')
        vix_note = '공포 상승 ↑' if vix['change'] > 0 else '공포 완화 ↓'
        vix_html = f'''
<div class="mcd-card">
  <div class="mcd-card-title">🌡 VIX (공포지수)</div>
  <div class="mcd-score" style="color:{vix_col}">{vix["price"]:.2f}</div>
  <div class="mcd-label" style="color:{vix_col}">{vix_note}</div>
  <div class="mcd-sub">{sign}{vix["change"]:.2f} &nbsp;({sign}{vix["pct"]:.1f}%) 전일 대비</div>
</div>'''
    else:
        vix_html = '<div class="mcd-card"><div class="mcd-card-title">🌡 VIX</div><div class="mcd-na">조회 실패</div></div>'

    # ── CFTC COT ─────────────────────────────────────────────
    if cot:
        net_val  = cot['net']
        net_str  = f'+{net_val:,}' if net_val >= 0 else f'{net_val:,}'
        cot_col  = '#00838f' if net_val >= 0 else '#c62828'
        cot_html = f'''
<div class="mcd-card mcd-card-wide">
  <div class="mcd-card-title">🏦 스마트 머니 (CFTC COT E-mini S&amp;P 500)</div>
  <div class="mcd-score" style="color:{cot_col}">{net_str}</div>
  <div class="mcd-label" style="color:{cot_col}">{cot["direction"]}</div>
  <div class="mcd-sub">Leveraged Funds — Long: {cot["lev_long"]:,} / Short: {cot["lev_short"]:,} &nbsp;({cot["date"]} 기준)</div>
  <div class="mcd-hint">헤지펀드 순포지션. 양수=순매수 우위, 음수=순매도 우위 (매주 금요일 갱신)</div>
</div>'''
    else:
        cot_html = '<div class="mcd-card mcd-card-wide"><div class="mcd-card-title">🏦 스마트 머니 (CFTC COT)</div><div class="mcd-na">조회 실패 (매주 금요일 갱신, 3일 시차)</div></div>'

    # ── Yahoo Headlines ───────────────────────────────────────
    if headlines:
        # 그룹별 소제목 + 아이템
        hl_parts = []
        cur_label = None
        for h in headlines:
            lbl = h.get('label', '🏢 개별종목')
            if lbl != cur_label:
                cur_label = lbl
                # 레이블별 색상
                lbl_color = {
                    '🚨 지정학속보': '#c62828',
                    '📊 거시경제':   '#00838f',
                    '📈 시장전반':   '#1a5c3a',
                    '🏢 개별종목':   '#7a7060',
                }.get(lbl, '#7a7060')
                hl_parts.append(
                    f'<li class="hl-group-title" style="color:{lbl_color}">{lbl}</li>'
                )
            title_esc = h['title'].replace('<', '&lt;').replace('>', '&gt;')
            hl_parts.append(
                f'<li><a href="{h["url"]}" target="_blank" rel="noopener">'
                f'{title_esc}</a> <span class="hl-date">{h["date"]}</span></li>'
            )
        hl_items = '\n'.join(hl_parts)
        hl_html = f'''
<div class="mcd-headlines">
  <div class="mcd-card-title">📰 주요 거시/증시 헤드라인 (Yahoo Finance)</div>
  <ul class="hl-list">{hl_items}</ul>
</div>'''
    else:
        hl_html = '<div class="mcd-headlines"><div class="mcd-card-title">📰 Yahoo Finance 헤드라인</div><div class="mcd-na">조회 실패</div></div>'

    return f'''
<section class="macro-section">
  <div class="macro-inner">
    <h2 class="macro-title">🌐 Macro &amp; Flow Dashboard</h2>
    <div class="mcd-grid">
      {fg_html}
      {vix_html}
      {cot_html}
    </div>
    {hl_html}
  </div>
</section>'''


def generate_html(posts: list, md_text: str, ts: str,
                  seeds: dict, stats: dict,
                  macro_data: dict | None = None) -> str:
    """전체 HTML 페이지 생성"""
    today      = datetime.now().strftime('%Y-%m-%d')
    md_fn      = f'{today}.md'
    cards_html = build_cards_html(posts)
    md_json    = json.dumps(md_text)
    macro_html = build_macro_html(macro_data) if macro_data else ''

    cnt_seed   = sum(1 for p in posts if p['source'] == 'seed')
    cnt_reddit = sum(1 for p in posts if p['source'] == 'reddit')

    seed_feeds = []
    if os.path.exists(SEED_LIST):
        with open(SEED_LIST, 'r', encoding='utf-8') as f:
            sl = json.load(f)
        seed_feeds = sl.get('feeds', [])

    seeds_info = ', '.join(
        f"{fd.get('name', urlhost(fd.get('rss_url','')))} ({urlhost(fd.get('rss_url',''))})"
        for fd in seed_feeds
    ) or '(등록된 피드 없음 — seed_list.json에 추가하세요)'

    subreddits_info = ', '.join(f'r/{s}' for s in seeds.get('reddit_subreddits', []))

    stat_html = (
        f"최종저장 <b>{stats['final']}</b>건 &nbsp;|&nbsp; "
        f"봇·공지 <b>{stats['filtered_bot']}</b>건 &nbsp;|&nbsp; "
        f"72h초과 <b>{stats['filtered_stale']}</b>건 &nbsp;|&nbsp; "
        f"단문 <b>{stats['filtered_short']}</b>건 &nbsp;|&nbsp; "
        f"자산+방향미충족 <b>{stats['filtered_no_signal']}</b>건 제거"
    )

    _css = """
  body {
    background: #f5f4ef;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
    color: #2c2a25;
    min-height: 100vh;
  }

  .site-header {
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 18px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 1px 6px rgba(0,0,0,.06);
  }
  .site-title { font-size: 22px; font-weight: 700; color: #3b3529; }
  .site-subtitle { font-size: 13px; color: #7a7060; margin-top: 2px; }
  .header-right { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 9px 18px; border-radius: 8px;
    font-size: 14px; font-weight: 600; cursor: pointer; border: none;
    transition: all .15s; text-decoration: none;
  }
  .btn-primary  { background: #4a3f2f; color: #fff; }
  .btn-primary:hover  { background: #5c4f3a; transform: translateY(-1px); }
  .btn-secondary { background: #fff; color: #4a3f2f; border: 1.5px solid #c8c0ae; }
  .btn-secondary:hover { background: #f0ede5; transform: translateY(-1px); }
  .btn-success  { background: #1a5c3a; color: #fff; }
  .btn-success:hover  { background: #236946; transform: translateY(-1px); }
  .btn.copied   { background: #1a5c3a !important; }

  .stats-bar {
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 10px 24px;
    font-size: 13px;
    color: #6b6052;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .stats-bar b { color: #3b3529; }

  .filter-summary {
    background: #fdf9f1;
    border-bottom: 1px solid #e4e1d8;
    padding: 8px 24px;
    font-size: 12px;
    color: #8a7d6a;
  }

  .cnt-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 10px; border-radius: 10px;
    font-size: 12px; font-weight: 700;
  }
  .cnt-seed   { background:#edf7ee; color:#2e7d32; }
  .cnt-reddit { background:#fff1ee; color:#c94b2b; }

  .filter-bar { padding: 14px 24px 0; display: flex; gap: 8px; flex-wrap: wrap; }
  .filter-btn {
    padding: 6px 16px; border-radius: 20px;
    border: 1.5px solid #d4cfc5; background: #fff;
    font-size: 13px; font-weight: 500; cursor: pointer; color: #5a5040;
    transition: all .12s;
  }
  .filter-btn:hover { background: #ebe8e0; }
  .filter-btn.active { background: #4a3f2f; color: #fff; border-color: #4a3f2f; }

  .main { max-width: 900px; margin: 0 auto; padding: 20px 20px 60px; }
  .cards { display: flex; flex-direction: column; gap: 14px; margin-top: 18px; }

  .card {
    background: #fff; border: 1px solid #e4e1d8;
    border-radius: 12px; padding: 18px 20px;
    transition: box-shadow .15s, transform .1s;
  }
  .card:hover { box-shadow: 0 4px 18px rgba(0,0,0,.08); transform: translateY(-1px); }
  .card.seed-card { border-left: 3px solid #2e7d32; }
  .card.hidden { display: none; }

  .card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 700; border: 1px solid; letter-spacing: .3px;
  }
  .card-label { font-size: 12px; color: #8a7d6a; flex: 1; }
  .card-date  { font-size: 12px; color: #aaa098; white-space: nowrap; }

  .card-title {
    display: block; font-size: 16px; font-weight: 600; color: #2c2a25;
    line-height: 1.45; text-decoration: none; margin-bottom: 6px;
  }
  .card-title:hover { color: #6b4f2a; text-decoration: underline; }
  .card-meta { font-size: 12px; color: #8a7d6a; margin-bottom: 10px; }

  .excerpt {
    font-size: 13.5px; color: #5a5040; line-height: 1.65;
    background: #f9f8f4; border-left: 3px solid #d4cfc5;
    padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 12px;
  }
  .card-footer { text-align: right; }
  .link-btn { font-size: 13px; color: #6b4f2a; text-decoration: none; font-weight: 500; }
  .link-btn:hover { text-decoration: underline; }

  .info-panel {
    background: #fff; border: 1px solid #e4e1d8; border-radius: 12px;
    padding: 16px 20px; margin-top: 28px; font-size: 13px; color: #6b6052; line-height: 1.9;
  }
  .info-panel h3 { font-size: 14px; font-weight: 600; color: #3b3529; margin-bottom: 8px; }
  .info-panel code { background: #f0ede5; padding: 2px 6px; border-radius: 4px; font-size: 12px; }

  .empty { text-align: center; padding: 60px 20px; color: #8a7d6a; font-size: 16px; }

  /* ── Macro Dashboard ── */
  .macro-section {
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 20px 24px 22px;
  }
  .macro-inner { max-width: 900px; margin: 0 auto; }
  .macro-title {
    font-size: 16px; font-weight: 700; color: #3b3529;
    margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
  }
  .mcd-grid {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
  }
  .mcd-card {
    background: #fdf9f1; border: 1px solid #e4e1d8; border-radius: 10px;
    padding: 14px 18px; min-width: 170px; flex: 1;
  }
  .mcd-card-wide { flex: 2 1 320px; }
  .mcd-card-title {
    font-size: 12px; font-weight: 600; color: #8a7d6a;
    text-transform: uppercase; letter-spacing: .4px; margin-bottom: 6px;
  }
  .mcd-score {
    font-size: 32px; font-weight: 800; line-height: 1.1; margin-bottom: 2px;
  }
  .mcd-label { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
  .mcd-sub   { font-size: 12px; color: #6b6052; margin-top: 4px; }
  .mcd-hint  { font-size: 11px; color: #aaa098; margin-top: 6px; line-height: 1.5; }
  .mcd-na    { font-size: 13px; color: #aaa098; padding: 10px 0; }
  .mcd-prev  { font-size: 12px; color: #8a7d6a; }
  .mcd-bar-wrap { margin-top: 8px; }
  .mcd-bar-bg {
    height: 8px; background: #e4e1d8; border-radius: 4px; overflow: hidden;
    margin-bottom: 4px;
  }
  .mcd-bar-fill { height: 100%; border-radius: 4px; transition: width .5s; }
  .mcd-bar-range {
    display: flex; justify-content: space-between;
    font-size: 10px; color: #aaa098; margin-bottom: 6px;
  }
  .mcd-headlines {
    background: #fdf9f1; border: 1px solid #e4e1d8; border-radius: 10px;
    padding: 14px 18px;
  }
  .hl-list { list-style: none; padding: 0; margin: 8px 0 0; }
  .hl-list li {
    padding: 6px 0; border-bottom: 1px solid #eeebe3;
    font-size: 13.5px; line-height: 1.5;
    display: flex; justify-content: space-between; align-items: baseline; gap: 10px;
  }
  .hl-list li:last-child { border-bottom: none; }
  .hl-list a { color: #3b3529; text-decoration: none; flex: 1; }
  .hl-list a:hover { color: #6b4f2a; text-decoration: underline; }
  .hl-date { font-size: 11px; color: #aaa098; white-space: nowrap; }
  .hl-group-title {
    padding: 8px 0 3px; border-bottom: none;
    font-size: 11px; font-weight: 700; letter-spacing: .4px;
    text-transform: uppercase; pointer-events: none;
  }
  #toast {
    position: fixed; bottom: 30px; left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: #2c2a25; color: #fff;
    padding: 10px 22px; border-radius: 24px; font-size: 14px;
    opacity: 0; transition: all .3s; pointer-events: none; z-index: 9999;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  @media (max-width: 600px) {
    .site-header { padding: 14px 16px; }
    .main { padding: 14px 12px 50px; }
    .filter-bar { padding: 12px 12px 0; }
    .card { padding: 14px 16px; }
    .btn { padding: 8px 14px; font-size: 13px; }
  }
"""
    return html_head(f'Alpha Hunter — {today}', css=_css) + f'''
<body>

<header class="site-header">
  <div>
    <div class="site-title">🎯 Alpha Hunter</div>
    <div class="site-subtitle">수집 시각: {ts} KST &nbsp;|&nbsp; {today}</div>
  </div>
  <div class="header-right">
    <button class="btn btn-primary" onclick="copyAll()" id="copyBtn">📋 전체 복사</button>
    <button class="btn btn-success" onclick="downloadMd()">⬇ MD 다운로드</button>
  </div>
</header>

<div class="stats-bar">
  📊 {stat_html}
  &nbsp;&nbsp;
  <span class="cnt-badge cnt-seed">시드 {cnt_seed}</span>
  <span class="cnt-badge cnt-reddit">Reddit {cnt_reddit}</span>
</div>

<div class="filter-summary">
  <b>시드 피드:</b> {seeds_info} &nbsp;|&nbsp;
  <b>서브레딧:</b> {subreddits_info}
</div>

{macro_html}

<div class="filter-bar">
  <button class="filter-btn active" onclick="filterCards(this,'all')">전체 {len(posts)}</button>
  <button class="filter-btn" onclick="filterCards(this,'seed')">시드 피드 {cnt_seed}</button>
  <button class="filter-btn" onclick="filterCards(this,'reddit')">Reddit {cnt_reddit}</button>
</div>

<div class="main">
  <div class="cards" id="cards">
    {cards_html}
  </div>

  <div class="info-panel">
    <h3>⚙ 수집 설정 안내</h3>
    <b>시드 피드 추가:</b> <code>seed_list.json</code>의 feeds 배열에 등록<br>
    &nbsp;&nbsp;예시: <code>{{"name": "홍길동", "rss_url": "https://rss.blog.naver.com/blogID"}}</code><br>
    <b>서브레딧 변경:</b> <code>alpha_hunter_seeds.json</code> 수정<br>
    <b>필터 기준:</b> 72시간 이내 | 본문 150자+ | 봇·공지 제외 | 예측·자산 키워드 OR 조건
  </div>
</div>

<div id="toast"></div>

<script>
const MD_CONTENT = {md_json};
const MD_FILENAME = '{md_fn}';

function showToast(msg, ms) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms || 2500);
}}

function copyAll() {{
  navigator.clipboard.writeText(MD_CONTENT).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ 복사 완료!';
    btn.classList.add('copied');
    showToast('클립보드 복사 완료! AI에 바로 붙여넣으세요.', 3000);
    setTimeout(() => {{ btn.textContent = '📋 전체 복사'; btn.classList.remove('copied'); }}, 2500);
  }}).catch(() => {{
    const ta = document.createElement('textarea');
    ta.value = MD_CONTENT;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('복사 완료!', 2000);
  }});
}}

function downloadMd() {{
  const blob = new Blob([MD_CONTENT], {{ type: 'text/markdown;charset=utf-8' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = MD_FILENAME;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast(MD_FILENAME + ' 다운로드 시작!', 2000);
}}

function filterCards(btn, source) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#cards .card').forEach(card => {{
    card.classList.toggle('hidden',
      source !== 'all' && card.dataset.source !== source);
  }});
}}
</script>
</body>
</html>'''


__all__ = [
    'build_cards_html',
    'build_macro_html',
    'generate_html',
    'SOURCE_COLORS', 'SOURCE_LABELS_MAP',
]
