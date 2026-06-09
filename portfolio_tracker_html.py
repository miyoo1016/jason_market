"""포트폴리오 트래커 — HTML 생성 모듈
대시보드 카드 + Squarified Treemap 히트맵"""

import json

from jm_lib.html_styles import html_head
from portfolio_tracker_base import (
    calc_daily_return_pct,
    format_daily_pnl_with_pct,
    format_total_pnl_with_pct,
)


def _pnl_color(val) -> str:
    """손익 색상 (CLAUDE.md 규칙: teal/red)"""
    return '#00838f' if val >= 0 else '#c62828'


def _pnl_bg(val) -> str:
    """손익 배경 색상"""
    return '#f0fff4' if val >= 0 else '#fff0f0'


def _sign(val) -> str:
    """양수 부호 추가 (음수는 자체 부호)"""
    return '+' if val >= 0 else ''


def _build_account_sections(accounts_data: dict) -> str:
    """계좌별 카드 섹션 HTML"""
    import os
    debug_mode = os.environ.get('JM_DEBUG_PRICE_SOURCE') == '1'
    wife_sections = []
    jason_sections = []
    for acc, d in accounts_data.items():
        rows_html = ''
        for r in d['rows']:
            if r['is_cash']:
                rows_html += f"""
      <tr class="cash-row">
        <td class="name-cell">{r['name']}<span class="fx-tag" style="background:#e8f5e9;color:#2e7d32;margin-left:4px">예금</span></td>
        <td class="center">현금</td>
        <td class="num" style="color:#888">{r['avg']}</td>
        <td class="num" style="color:#888">{r['price']}</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:#888">-</td>
        <td class="num" style="color:#888">-</td>
      </tr>"""
            else:
                pc = _pnl_color(r['profit_krw'])
                pdc = _pnl_color(r['daily_profit_krw'])
                daily_html = format_daily_pnl_with_pct(r['daily_profit_krw'], r['val_krw'])
                profit_html = format_total_pnl_with_pct(r['profit_krw'], r['pct'])
                # USD의 경우 환차 이익 표시 태그 추가
                fx_info = ""
                if r['cur'] == 'USD' and abs(r.get('fx_pnl', 0)) > 100:
                    fxc = _pnl_color(r['fx_pnl'])
                    fx_info = (f'<br><span class="fx-tag" style="color:{fxc};'
                               f'background:none;padding:0">환차 '
                               f'{_sign(r["fx_pnl"])}₩{r["fx_pnl"]:,.0f}</span>')

                precision_tag = ('<span class="fx-tag" style="background:#e0f2f1;'
                                 'color:#00695c">정밀</span>' if r.get('is_precision') else "")
                source_tag = ''
                if r.get('price_is_fallback') or 'mapping' in str(r.get('price_fallback_reason', '')).lower() or r.get('price_is_mapping_warning'):
                    source_tag += '<br><span class="fx-tag" style="background:#fff3e0;color:#e65100">⚠ fallback</span>'
                if r.get('price_stale_warning'):
                    if not source_tag: source_tag += '<br>'
                    source_tag += '<span class="fx-tag" style="background:#ffebee;color:#c62828">⚠ stale</span>'

                if debug_mode and r.get('price_source'):
                    if r.get('price_is_fallback'):
                        source_tag += (
                            f'<br><span class="price-source">source={r.get("price_source")} '
                            f'read_time={r.get("price_read_time", "")} '
                            f'stale_warning={r.get("price_stale_warning", "")} '
                            f'fallback_reason={r.get("price_fallback_reason", "")}</span>'
                        )
                    else:
                        source_tag += (
                            f'<br><span class="price-source">source={r.get("price_source")} '
                            f'quote_time={r.get("price_quote_time", "")}</span>'
                        )

                rows_html += f"""
      <tr>
        <td class="name-cell">{r['name']}{precision_tag}{fx_info}</td>
        <td class="num center">{r['qty']}</td>
        <td class="num">{r['avg']}</td>
        <td class="num">{r['price']}{source_tag}</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:{pdc}">{daily_html}</td>
        <td class="num" style="color:{pc}">{profit_html}</td>
      </tr>"""

        has_profit_basis = d.get('profit_basis', d['cost']) > 0
        acc_col = _pnl_color(d['profit'])
        acc_dcol = _pnl_color(d['daily_profit'])
        acc_bg = _pnl_bg(d['profit'])
        acc_profit_html = (
            f'<span class="acc-pnl acc-head-cell num" style="color:{acc_col}">'
            f'총 {format_total_pnl_with_pct(d["profit"], d["pct"])}</span>'
            if has_profit_basis else
            '<span class="acc-pnl acc-head-cell num" style="color:#888">총 -</span>'
        )
        acc_daily_html = (
            f'<span class="acc-pnl acc-head-cell num" style="color:{acc_dcol}">'
            f'1일 {format_daily_pnl_with_pct(d["daily_profit"], d["curr"])}</span>'
            if has_profit_basis else
            '<span class="acc-pnl acc-head-cell num" style="color:#888">1일 -</span>'
        )
        acc_profit_cell = (
            f'<td class="num" style="color:{acc_col};font-weight:700">{format_total_pnl_with_pct(d["profit"], d["pct"])}</td>'
            if has_profit_basis else
            '<td class="num" style="color:#888;font-weight:700">-</td>'
        )
        acc_daily_cell = (
            f'<td class="num" style="color:{acc_dcol};font-weight:700">{format_daily_pnl_with_pct(d["daily_profit"], d["curr"])}</td>'
            if has_profit_basis else
            '<td class="num" style="color:#888;font-weight:700">-</td>'
        )
        card_html = f"""
  <div class="acc-card">
    <div class="acc-header">
      <span class="acc-name acc-head-cell">{acc}</span>
      <span class="acc-head-cell"></span>
      <span class="acc-head-cell"></span>
      <span class="acc-head-cell"></span>
      <span class="acc-val acc-head-cell num">₩{d['curr']:,.0f}</span>
      {acc_daily_html}
      {acc_profit_html}
    </div>
    <table>
      <colgroup>
        <col class="col-name"><col class="col-qty"><col class="col-avg"><col class="col-price">
        <col class="col-value"><col class="col-daily"><col class="col-profit">
      </colgroup>
      <thead>
        <tr>
          <th>종목</th><th class="center">수량</th><th class="num">평단가</th><th class="num">현재가</th>
          <th class="num">평가금액</th><th class="num">1일손익</th><th class="num">총손익</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr style="background:{acc_bg}">
          <td colspan="4" style="font-weight:700;padding:10px 12px">계좌 합계</td>
          <td class="num" style="font-weight:700">₩{d['curr']:,.0f}</td>
          {acc_daily_cell}
          {acc_profit_cell}
        </tr>
      </tfoot>
    </table>
  </div>"""
        if '와이프' in acc:
            wife_sections.append(card_html)
        else:
            jason_sections.append(card_html)
    return f"""
  <div class="account-grid" id="account-grid">
    <div class="account-column account-column-wife">{''.join(wife_sections)}</div>
    <div class="account-column account-column-jason">{''.join(jason_sections)}</div>
  </div>"""


def _build_heatmap_data(accounts_data: dict) -> str:
    """히트맵 JS 데이터 (같은 종목 여러 계좌 합산, 가중 평균)"""
    merged = {}  # name → dict
    for acc, d in accounts_data.items():
        for r in d['rows']:
            name = r['name']
            val = r['val_krw']
            daily_krw = r['daily_profit_krw']
            profit_krw = r['profit_krw']
            pct = r['pct']
            daily_pct = calc_daily_return_pct(val, daily_krw) or 0
            is_cash = r['is_cash']

            if name in merged:
                ex = merged[name]
                old_val = ex['val']
                total_val = old_val + val
                ex['pct'] = (ex['pct'] * old_val + pct * val) / total_val if total_val else 0
                ex['daily_krw'] += daily_krw
                ex['profit_krw'] += profit_krw
                ex['daily_pct'] = ex['daily_krw'] / total_val * 100 if total_val else 0
                ex['val'] = total_val
                if acc not in ex['acc']:
                    ex['acc'] += ' + ' + acc
            else:
                merged[name] = {
                    'name': name,
                    'pct': pct,
                    'daily_pct': daily_pct,
                    'val': val,
                    'daily_krw': daily_krw,
                    'profit_krw': profit_krw,
                    'price': r.get('price', ''),
                    'acc': acc,
                    'is_cash': is_cash,
                }

    # 최종 반올림
    items = []
    for it in merged.values():
        items.append({
            'name': it['name'],
            'pct': round(it['pct'], 2),
            'daily_pct': round(it['daily_pct'], 2),
            'val': round(it['val']),
            'daily_krw': round(it['daily_krw']),
            'profit_krw': round(it['profit_krw']),
            'price': it['price'],
            'acc': it['acc'],
            'is_cash': it['is_cash'],
        })
    return json.dumps(items, ensure_ascii=False)


def generate_html(accounts_data: dict, usdkrw_tuple: tuple, timestamp: str) -> str:
    """전체 포트폴리오 대시보드 HTML 생성"""
    usdkrw, prev_usdkrw = usdkrw_tuple
    grand_curr = sum(d['curr'] for d in accounts_data.values())
    grand_daily = sum(d['daily_profit'] for d in accounts_data.values())
    grand_profit = sum(d['profit'] for d in accounts_data.values())
    grand_basis = sum(d.get('profit_basis', d['cost']) for d in accounts_data.values())
    grand_pct = grand_profit / grand_basis * 100 if grand_basis > 0 else 0
    grand_usd = grand_curr / usdkrw

    account_sections = _build_account_sections(accounts_data)
    heatmap_json = _build_heatmap_data(accounts_data)
    fallback_rows = [
        r['name']
        for d in accounts_data.values()
        for r in d['rows']
        if r.get('price_is_fallback')
    ]
    audit_ok = len(fallback_rows) == 0
    audit_text = f" · Price audit {'OK' if audit_ok else 'WARN'} · fallback {len(fallback_rows)}"
    fallback_note = (
        f"<br><strong>가격 경고:</strong> GoogleSheetFallback 사용 "
        f"({', '.join(sorted(set(fallback_rows)))})"
        if fallback_rows else ''
    )

    gpc = _pnl_color(grand_profit)
    gdc = _pnl_color(grand_daily)
    grand_daily_html = format_daily_pnl_with_pct(grand_daily, grand_curr)
    grand_profit_html = format_total_pnl_with_pct(grand_profit, grand_pct)

    _css = """
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f6f8;color:#222;font-size:14px;margin:0}
.header{background:#1a1a2e;color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.header-text{flex:1}
.header h1{font-size:20px;font-weight:700}
.header .sub{font-size:12px;color:#aaa;margin-top:3px}
.header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.btn-heatmap,.btn-layout{padding:8px 18px;background:#00838f;color:#fff;border:none;border-radius:7px;
              cursor:pointer;font-size:13px;font-weight:700;letter-spacing:.3px;
              box-shadow:0 2px 8px rgba(0,0,0,.25);transition:background .2s;white-space:nowrap}
.btn-heatmap:hover,.btn-layout:hover{background:#00696f}
.btn-heatmap.active,.btn-layout.active{background:#e65100}
.btn-heatmap.active:hover,.btn-layout.active:hover{background:#bf4000}
.container{width:calc(100vw - 48px);max-width:1320px;margin:0 auto;padding:12px 0 60px}
body.layout-split .container{width:calc(100vw - 24px);max-width:none}
body.layout-stack .container{width:calc(100vw - 48px);max-width:1320px}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-bottom:20px}
.price-basis-note{background:#fff;border-left:4px solid #00838f;border-radius:8px;padding:10px 14px;
                  box-shadow:0 1px 4px rgba(0,0,0,.08);font-size:12px;color:#555;margin:-8px 0 16px}
.sbox{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.sbox.grand{background:#1a1a2e;color:#fff}
.sbox .sl{font-size:11px;color:#999;margin-bottom:5px}
.sbox.grand .sl{color:#aaa}
.sbox .sv{font-size:22px;font-weight:800;line-height:1.1}
.sbox .sv2{font-size:12px;color:#888;margin-top:4px}
.sbox.grand .sv2{color:#aaa}
.account-grid{width:100%;display:grid;grid-template-columns:1fr;gap:14px;align-items:start}
.account-grid.layout-stack{grid-template-columns:1fr}
.account-grid.layout-split{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.account-column{width:100%;min-width:0}
@media(max-width:900px){
  .account-grid.layout-split{grid-template-columns:1fr}
}
.acc-card{width:100%;min-width:0;background:#fff;border-radius:10px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow-x:auto;overflow-y:hidden}
.acc-header{display:grid;grid-template-columns:24% 7% 9% 9% 16% 17.5% 17.5%;align-items:center;background:#fafafa;border-bottom:1px solid #eee}
.acc-head-cell{padding:10px 12px;min-width:0}
.acc-name{font-size:14px;font-weight:700}
.acc-val{font-size:15px;font-weight:700}
.acc-pnl{font-size:13px;font-weight:600}
table{width:100%;border-collapse:collapse;table-layout:fixed}
.col-name{width:24%}.col-qty{width:7%}.col-avg{width:9%}.col-price{width:9%}.col-value{width:16%}.col-daily{width:17.5%}.col-profit{width:17.5%}
th{background:#f5f5f5;padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#888;white-space:nowrap;border-bottom:2px solid #eee}
td{padding:10px 12px;border-bottom:1px solid #f5f5f5;font-size:13px}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafafa}
.cash-row td{color:#888;background:#fafffe}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pct{font-weight:600}
.center{text-align:center}
.name-cell{font-weight:600}
.fx-tag{font-size:10px;padding:2px 4px;background:#f0f7ff;color:#0056b3;border-radius:3px;margin-left:4px}
.price-source{display:block;font-size:10px;color:#888;font-weight:500;margin-top:2px}
.footer{text-align:center;font-size:11px;color:#bbb;margin-top:30px}
.acc-header,table{min-width:860px}

/* ── 히트맵 ────────────────────────────────────────────── */
#heatmap-view{display:none;margin-bottom:20px}
#heatmap-view.show{display:block}
.hm-wrap{
  background:#fff;border-radius:12px;padding:16px 16px 12px;
  box-shadow:0 1px 6px rgba(0,0,0,.08);
}
.hm-header{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.hm-title{font-size:12px;color:#666;font-weight:600;letter-spacing:.4px;flex:1}
.hm-tabs{display:flex;gap:6px}
.hm-tab{
  padding:5px 14px;font-size:12px;font-weight:700;border:none;
  border-radius:5px;cursor:pointer;transition:background .15s,color .15s;
  background:#f0f2f5;color:#666;
}
.hm-tab.active{background:#00838f;color:#fff}
#hm-canvas{
  position:relative;width:100%;height:520px;overflow:hidden;border-radius:6px;
}
.hm-tile{position:absolute;box-sizing:border-box;padding:2px;cursor:default;}
.hm-inner{
  width:100%;height:100%;border-radius:5px;
  display:flex;flex-direction:column;justify-content:center;align-items:center;
  overflow:hidden;transition:filter .15s,background .35s;
  gap:1px;
}
.hm-tile:hover .hm-inner{filter:brightness(1.18) saturate(1.1);}
.hm-name{
  font-size:11px;font-weight:600;color:rgba(255,255,255,.82);
  text-shadow:0 1px 4px rgba(0,0,0,.7);letter-spacing:.5px;
  text-align:center;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:92%;
  text-transform:uppercase;
}
.hm-pct{
  font-size:18px;font-weight:900;color:#fff;
  text-shadow:0 2px 8px rgba(0,0,0,.55),0 1px 2px rgba(0,0,0,.4);
  margin-top:2px;line-height:1;letter-spacing:-.3px;
}
.hm-val{
  font-size:11px;font-weight:600;color:rgba(255,255,255,.78);
  text-shadow:0 1px 4px rgba(0,0,0,.6);margin-top:3px;
}
.hm-amount{
  font-size:10px;font-weight:500;color:rgba(255,255,255,.65);
  text-shadow:0 1px 3px rgba(0,0,0,.5);margin-top:1px;
}
.hm-legend{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:11px;color:#888}
.hm-legend-bar{
  flex:1;height:8px;border-radius:4px;
  background:linear-gradient(to right,
    #ff3c3c,#c62828,#5a1a1a,#1a2a1a,#1a6e3a,#00dc5a);
}
"""
    html = html_head('Jason Market — 포트폴리오 손익', css=_css) + f"""
<body>
<div class="header">
  <div class="header-text">
    <h1>Jason Market — 포트폴리오 손익</h1>
    <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 실시간 환율 ₩{usdkrw:,.2f}/USD</div>
  </div>
  <div class="header-actions">
    <button class="btn-layout" id="btn-layout" onclick="toggleAccountLayout()">상하 보기</button>
    <button class="btn-heatmap" id="btn-hm" onclick="toggleHeatmap()">🟦 히트맵 보기</button>
  </div>
</div>
<div class="container">
  <!-- 히트맵 뷰 -->
  <div id="heatmap-view">
    <div class="hm-wrap">
      <div class="hm-header">
        <div class="hm-title">PORTFOLIO HEATMAP &nbsp;·&nbsp; 타일 크기 = 평가금액 비중</div>
        <div class="hm-tabs">
          <button class="hm-tab active" id="tab-total" onclick="switchMode('total')">📊 총 수익률</button>
          <button class="hm-tab"        id="tab-daily" onclick="switchMode('daily')">📅 일일 수익률</button>
        </div>
      </div>
      <div id="hm-canvas"></div>
      <div class="hm-legend">
        <span style="color:#ff3c3c">▼ 대폭 하락</span>
        <div class="hm-legend-bar"></div>
        <span style="color:#00dc5a">▲ 대폭 상승</span>
        &nbsp;|&nbsp;<span>색상 기준 ±10%</span>
      </div>
    </div>
  </div>

  <div id="table-view">
  <div class="summary">
    <div class="sbox grand">
      <div class="sl">총 평가금액</div>
      <div class="sv">₩{grand_curr:,.0f}</div>
      <div class="sv2">${grand_usd:,.0f}</div>
    </div>
    <div class="sbox" style="border-left:4px solid {gdc}">
      <div class="sl">총 1일 손익 (주가+환율)</div>
      <div class="sv" style="color:{gdc}">{grand_daily_html}</div>
      <div class="sv2" style="color:#888">전일 환율 ₩{prev_usdkrw:,.2f} 대비</div>
    </div>
    <div class="sbox" style="border-left:4px solid {gpc}">
      <div class="sl">총 손익</div>
      <div class="sv" style="color:{gpc}">{grand_profit_html}</div>
    </div>
  </div>
  <div class="price-basis-note">
    가격 기준: canonical live price map · 국내주식/ETF: naver_live 우선 · 미국주식/ETF: yahoo_quote · 수동/현금: GoogleSheet{audit_text}
    {fallback_note}
  </div>
  {account_sections}
  <div class="footer">Jason Market · {timestamp} · 구글드라이브 자산계산기.xlsx 자동 동기화</div>
  </div><!-- /table-view -->
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#00838f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.2)">📋 전체 복사</button>
<script>
var _hmData = {heatmap_json};
var _hmBuilt = false;
var _layoutKey = 'portfolio_layout_mode';

function _savedLayoutMode() {{
  try {{
    var saved = window.localStorage.getItem(_layoutKey);
    if (saved === 'split' || saved === 'stack') return saved;
  }} catch (e) {{}}
  return window.innerWidth >= 1600 ? 'split' : 'stack';
}}

function setAccountLayout(mode, persist) {{
  var grid = document.getElementById('account-grid');
  var btn = document.getElementById('btn-layout');
  if (!grid || !btn) return;
  if (mode !== 'split') mode = 'stack';
  grid.classList.toggle('layout-split', mode === 'split');
  grid.classList.toggle('layout-stack', mode === 'stack');
  document.body.classList.toggle('layout-split', mode === 'split');
  document.body.classList.toggle('layout-stack', mode === 'stack');
  btn.textContent = mode === 'split' ? '상하 보기' : '좌우 보기';
  btn.classList.toggle('active', mode === 'split');
  if (persist) {{
    try {{ window.localStorage.setItem(_layoutKey, mode); }} catch (e) {{}}
  }}
}}

function toggleAccountLayout() {{
  var grid = document.getElementById('account-grid');
  var isSplit = grid && grid.classList.contains('layout-split');
  setAccountLayout(isSplit ? 'stack' : 'split', true);
}}

function initAccountLayout() {{
  setAccountLayout(_savedLayoutMode(), false);
}}

/* ═══════════════════════════════════════════════════════
   Squarified Treemap  (Bruls, Huizing, van Wijk 1999)
   ═══════════════════════════════════════════════════════ */
function squarify(nodes, x, y, w, h) {{
  var out = [];
  var sorted = nodes.slice().sort(function(a,b){{return b.val-a.val;}});

  function layout(items, rx, ry, rw, rh) {{
    if (!items.length || rw < 1 || rh < 1) return;
    if (items.length === 1) {{
      out.push({{item:items[0], x:rx, y:ry, w:rw, h:rh}});
      return;
    }}
    var sub   = items.reduce(function(s,i){{return s+i.val;}}, 0);
    var scale = rw * rh / sub;
    var short = Math.min(rw, rh);

    /* 최적 row 탐색 */
    var row=[], rowSum=0, prevW=Infinity, split=0;
    for (var k=0; k<items.length; k++) {{
      row.push(items[k]); rowSum+=items[k].val;
      var cur = worst(row, rowSum, short, scale);
      if (cur > prevW) {{ row.pop(); rowSum-=items[k].val; break; }}
      prevW=cur; split=k+1;
    }}

    /* row 배치 */
    var rowArea = rowSum * scale;
    if (rw <= rh) {{                        /* 가로 strip (위) */
      var sh = rowArea / rw, cx = rx;
      row.forEach(function(it) {{
        var iw = it.val / rowSum * rw;
        out.push({{item:it, x:cx, y:ry, w:iw, h:sh}}); cx+=iw;
      }});
      layout(items.slice(split), rx, ry+sh, rw, rh-sh);
    }} else {{                               /* 세로 strip (왼쪽) */
      var sw = rowArea / rh, cy = ry;
      row.forEach(function(it) {{
        var ih = it.val / rowSum * rh;
        out.push({{item:it, x:rx, y:cy, w:sw, h:ih}}); cy+=ih;
      }});
      layout(items.slice(split), rx+sw, ry, rw-sw, rh);
    }}
  }}

  function worst(row, rowSum, short, scale) {{
    var ra = rowSum*scale, sd = ra/short, w=0;
    row.forEach(function(it) {{
      var nd = it.val/rowSum*short;
      var r  = Math.max(sd/nd, nd/sd);
      if (r>w) w=r;
    }});
    return w;
  }}

  layout(sorted, x, y, w, h);
  return out;
}}

/* ══════════════════════════════════════════════════════
   색상 계산 (±10% 기준)
   ══════════════════════════════════════════════════════ */
function hmColor(pct) {{
  var t = Math.min(1, Math.abs(pct) / 10);
  var r, g, b;
  if (pct >= 0) {{
    r = Math.round(26  + (0   - 26 ) * t);
    g = Math.round(42  + (220 - 42 ) * t);
    b = Math.round(26  + (90  - 26 ) * t);
  }} else {{
    r = Math.round(42  + (255 - 42 ) * t);
    g = Math.round(26  + (60  - 26 ) * t);
    b = Math.round(26  + (60  - 26 ) * t);
  }}
  return 'rgb('+r+','+g+','+b+')';
}}

var _mode    = 'total';
var _tilRefs = [];

function fmtKrw(v) {{
  var sign = v >= 0 ? '+' : '-';
  var abs  = Math.abs(v);
  if (abs >= 1e8) return sign+'₩'+(abs/1e8).toFixed(1)+'억';
  if (abs >= 1e4) return sign+'₩'+Math.round(abs/1e4)+'만';
  return sign+'₩'+abs.toLocaleString();
}}
function fmtVal(v) {{
  if (v >= 1e8) return '₩'+(v/1e8).toFixed(1)+'억';
  return '₩'+Math.round(v/1e4)+'만';
}}

function buildHeatmap() {{
  if (_hmBuilt) return;
  _hmBuilt = true;

  var canvas = document.getElementById('hm-canvas');
  var W = canvas.offsetWidth || 900;
  var H = 520;
  var tiles = squarify(_hmData, 0, 0, W, H);

  tiles.forEach(function(t) {{
    var item    = t.item;
    var minSide = Math.min(t.w, t.h);

    var showName   = t.w > 45  && t.h > 30;
    var showPct    = t.w > 30  && t.h > 22;
    var showVal    = minSide > 58;
    var showAmount = minSide > 78;

    var fName   = Math.max(9,  Math.min(13, minSide*0.13)) + 'px';
    var fPct    = Math.max(11, Math.min(22, minSide*0.22)) + 'px';
    var fSub    = Math.max(8,  Math.min(12, minSide*0.11)) + 'px';

    var div = document.createElement('div');
    div.className = 'hm-tile';
    div.style.cssText = 'left:'+t.x+'px;top:'+t.y+'px;width:'+t.w+'px;height:'+t.h+'px';

    var inner = document.createElement('div');
    inner.className = 'hm-inner';

    if (showName) {{
      var el = document.createElement('div');
      el.className  = 'hm-name';
      el.style.fontSize = fName;
      el.textContent = item.is_cash ? '현금' : item.name;
      inner.appendChild(el);
    }}

    var pctEl = null;
    if (showPct) {{
      pctEl = document.createElement('div');
      pctEl.className = 'hm-pct';
      pctEl.style.fontSize = fPct;
      inner.appendChild(pctEl);
    }}

    if (showVal) {{
      var el = document.createElement('div');
      el.className = 'hm-val';
      el.style.fontSize = fSub;
      el.textContent = fmtVal(item.val);
      inner.appendChild(el);
    }}

    var amountEl = null;
    if (showAmount) {{
      amountEl = document.createElement('div');
      amountEl.className = 'hm-amount';
      amountEl.style.fontSize = fSub;
      inner.appendChild(amountEl);
    }}

    div.appendChild(inner);
    canvas.appendChild(div);

    _tilRefs.push({{
      inner:inner, pctEl:pctEl, amountEl:amountEl,
      div:div, item:item
    }});
  }});

  _applyMode();
}}

function _applyMode() {{
  _tilRefs.forEach(function(ref) {{
    var item = ref.item;
    var pct  = _mode === 'daily' ? item.daily_pct : item.pct;
    var sign = pct >= 0 ? '+' : '';

    ref.inner.style.background = item.is_cash ? '#546e7a' : hmColor(pct);

    if (ref.pctEl)
      ref.pctEl.textContent = item.is_cash ? '-' : (sign + pct.toFixed(2) + '%');

    if (ref.amountEl) {{
      if (item.is_cash) {{
        ref.amountEl.textContent = '';
      }} else if (_mode === 'daily') {{
        ref.amountEl.textContent = '일 ' + fmtKrw(item.daily_krw);
      }} else {{
        ref.amountEl.textContent = '총 ' + fmtKrw(item.profit_krw);
      }}
    }}

    ref.div.title =
      item.name +
      ' | ' + (_mode==='daily'?'일일':'총') + ' ' + sign + pct.toFixed(2) + '%' +
      ' | 평가 ' + fmtVal(item.val) +
      ' | 일 ' + fmtKrw(item.daily_krw) +
      ' | 총 ' + fmtKrw(item.profit_krw) +
      ' | ' + item.acc;
  }});
}}

function switchMode(mode) {{
  _mode = mode;
  document.getElementById('tab-total').classList.toggle('active', mode==='total');
  document.getElementById('tab-daily').classList.toggle('active', mode==='daily');
  if (_hmBuilt) _applyMode();
}}

function toggleHeatmap() {{
  var hv  = document.getElementById('heatmap-view');
  var tv  = document.getElementById('table-view');
  var btn = document.getElementById('btn-hm');
  if (hv.classList.contains('show')) {{
    hv.classList.remove('show');
    tv.style.display = '';
    btn.textContent = '🟦 히트맵 보기';
    btn.classList.remove('active');
  }} else {{
    buildHeatmap();
    hv.classList.add('show');
    tv.style.display = 'none';
    btn.textContent = '📋 테이블 보기';
    btn.classList.add('active');
    window.scrollTo({{top:0, behavior:'smooth'}});
  }}
}}

function copyReport() {{
  var el = document.querySelector('#table-view') || document.body;
  navigator.clipboard.writeText(el.innerText).then(function() {{
    var b = document.getElementById('copy-btn');
    b.textContent='✅ 복사 완료!'; b.style.background='#2e7d32';
    setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#00838f';}},2500);
  }}).catch(function() {{
    var t=document.createElement('textarea'); t.value=el.innerText;
    document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t);
  }});
}}
initAccountLayout();
</script>
</body>
</html>"""
    return html


__all__ = ['generate_html']
