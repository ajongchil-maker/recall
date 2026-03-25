"""
제품안전정보센터 리콜 정보 수집기 (API 키 불필요)
--auto 플래그: 브라우저/Enter 없이 자동 종료 (스케줄러용)
index.html 로 저장 → GitHub Pages URL 고정
"""

import requests
import re
import sys
import time
import os
import webbrowser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import DAYS_BACK, MAX_PAGES, OUTPUT_DIR, REQUEST_DELAY, FILTER_KEYWORDS

BASE      = "https://www.safetykorea.kr"
AUTO_MODE = "--auto" in sys.argv

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": BASE + "/recall/recallBoard",
    "Origin": BASE,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def matches_keywords(item):
    if not FILTER_KEYWORDS:
        return True
    target = " ".join([
        item.get("product_name", ""), item.get("model_name", ""),
        item.get("company", ""),      item.get("hazard", ""),
    ])
    return any(kw in target for kw in FILTER_KEYWORDS)


def matched_keywords(item):
    target = " ".join([
        item.get("product_name", ""), item.get("model_name", ""),
        item.get("company", ""),      item.get("hazard", ""),
    ])
    return [kw for kw in FILTER_KEYWORDS if kw in target]


def fetch_list_page(list_url, page_no, start_date, end_date):
    data = {"selectedOption":"6","startDate":start_date,"endDate":end_date,"pageNo":str(page_no)}
    try:
        resp = SESSION.post(list_url, data=data, timeout=15)
        resp.raise_for_status(); resp.encoding = "utf-8"
    except Exception as e:
        print(f"\n    ⚠️  목록 요청 실패: {e}"); return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for row in soup.select("table tr"):
        onclick = row.get("onclick", "")
        m = re.search(r"goDetail\('(\d+)'\)", onclick)
        if not m: continue
        recall_uid = m.group(1)
        cells = row.find_all("td")
        if len(cells) < 5: continue

        img_tag = cells[1].find("img")
        img_url = ""
        if img_tag:
            src = img_tag.get("src","")
            if src and "noimage" not in src:
                img_url = src if src.startswith("http") else BASE+src

        items.append({
            "recall_uid":   recall_uid,
            "product_name": cells[2].get_text(strip=True),
            "model_name":   cells[3].get_text(strip=True),
            "company":      cells[4].get_text(strip=True) if len(cells)>4 else "-",
            "recall_type":  cells[5].get_text(strip=True) if len(cells)>5 else "-",
            "pub_date":     cells[-1].get_text(strip=True),
            "img_url":      img_url,
            "hazard":       "",
        })
    return items


def collect_list(list_url, label, start_date, end_date):
    all_items = []
    print(f"\n  [{label}] 목록 수집 중...", end="", flush=True)
    for page in range(MAX_PAGES):
        items = fetch_list_page(list_url, page, start_date, end_date)
        all_items.extend(items)
        print(f" {page+1}p({len(items)}건)", end="", flush=True)
        if len(items) == 0: break
        time.sleep(REQUEST_DELAY)
    print(f"  → 총 {len(all_items)}건")
    return all_items


def fetch_detail(detail_url, recall_uid):
    try:
        resp = SESSION.post(detail_url, data={"recallUid":recall_uid}, timeout=15)
        resp.raise_for_status(); resp.encoding = "utf-8"
    except Exception as e:
        return {"hazard":f"로드 실패:{e}", "img_url":""}

    soup = BeautifulSoup(resp.text, "html.parser")
    hazard = ""
    for th in soup.find_all("th"):
        if any(k in th.get_text() for k in ["위해","결함","리콜사유"]):
            td = th.find_next_sibling("td")
            if td: hazard = td.get_text(separator=" ", strip=True); break
    if not hazard:
        for td in soup.find_all("td"):
            t = td.get_text(strip=True)
            if len(t)>20 and any(k in t for k in ["위해","결함","부적합","화재","감전","파손","부상"]):
                hazard = t; break

    img_url = ""
    for img in soup.find_all("img"):
        src = img.get("src","")
        if src and "office.safetykorea.kr" in src: img_url = src; break
    if not img_url:
        for img in soup.find_all("img"):
            src = img.get("src","")
            if src and "noimage" not in src and "icon" not in src and "btn" not in src and "logo" not in src and src.lower().endswith((".jpg",".jpeg",".png",".webp")):
                img_url = src if src.startswith("http") else BASE+src; break

    return {"hazard": hazard if hazard else "상세 페이지에서 확인하세요", "img_url": img_url}


def enrich_and_filter(items, detail_url, label):
    kw_label = f" [필터:{','.join(FILTER_KEYWORDS)}]" if FILTER_KEYWORDS else " [전체]"
    print(f"  [{label}] 상세+필터{kw_label} ({len(items)}건)...", flush=True)
    enriched = []
    for i, item in enumerate(items, 1):
        print(f"    {i:3d}/{len(items)}  {item['product_name'][:28]:<28}", end="\r", flush=True)
        detail = fetch_detail(detail_url, item["recall_uid"])
        merged = {**item, **{"hazard":detail["hazard"],"detail_url":f"{detail_url}?recallUid={item['recall_uid']}"}}
        if detail["img_url"]: merged["img_url"] = detail["img_url"]
        merged["matched"] = matched_keywords(merged)
        if matches_keywords(merged): enriched.append(merged)
        time.sleep(REQUEST_DELAY)
    print(f"    → 필터 후 {len(enriched)}건{' '*40}")
    return enriched


def highlight(text, keywords):
    for kw in keywords:
        text = text.replace(kw, f'<mark>{kw}</mark>')
    return text


def render_card(item, source_type):
    badge_cls = "b-dom" if source_type=="domestic" else "b-for"
    badge_lbl = "🇰🇷 국내 리콜" if source_type=="domestic" else "🌍 국외 리콜"
    kws       = item.get("matched",[])
    hazard    = highlight(item.get("hazard","상세 페이지에서 확인").replace("\n","<br>"), kws)
    pname     = highlight(item["product_name"], kws)
    kw_badges = "".join(f'<span class="kw">{k}</span>' for k in kws)
    img_html  = (
        f'<img src="{item["img_url"]}" alt="제품사진" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
        f'<div class="noimg">📦 이미지 없음</div>'
    ) if item.get("img_url") else '<div class="noimg">📦 이미지 없음</div>'

    return f"""<div class="card">
  <div class="cimg">{img_html}</div>
  <div class="cbody">
    <div class="ctop"><span class="badge {badge_cls}">{badge_lbl}</span><span class="date">📅 {item["pub_date"]}</span></div>
    <h3><a href="{item['detail_url']}" target="_blank">{pname}</a></h3>
    {f'<div class="kwrow">{kw_badges}</div>' if kw_badges else ''}
    <table class="info">
      <tr><th>모델명</th><td>{item["model_name"]}</td></tr>
      <tr><th>사업자</th><td>{item["company"]}</td></tr>
      <tr><th>리콜종류</th><td class="rtype">{item["recall_type"]}</td></tr>
    </table>
    <div class="hbox"><div class="hlabel">⚠️ 위해내용</div><div class="htext">{hazard}</div></div>
    <a href="{item['detail_url']}" target="_blank" class="dbtn">상세 페이지 보기 ↗</a>
  </div>
</div>"""


def generate_html(domestic, overseas, start_fmt, end_fmt):
    now    = datetime.now()
    today  = now.strftime("%Y년 %m월 %d일 %H:%M")
    # 다음 월요일 계산
    days_until_monday = (7 - now.weekday()) % 7 or 7
    next_monday = (now + timedelta(days=days_until_monday)).strftime("%Y년 %m월 %d일")
    total  = len(domestic)+len(overseas)
    kw_str = ", ".join(FILTER_KEYWORDS) if FILTER_KEYWORDS else "전체"
    all_c  = "".join(render_card(i,"domestic") for i in domestic)+"".join(render_card(i,"overseas") for i in overseas)
    dom_c  = "".join(render_card(i,"domestic") for i in domestic) or '<p class="empty">해당 키워드 국내 리콜 없음</p>'
    for_c  = "".join(render_card(i,"overseas") for i in overseas) or '<p class="empty">해당 키워드 국외 리콜 없음</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>리콜 정보 — {today}</title>
<style>
:root{{--p:#1a3c5e;--a:#2979b8;--w:#e65100;--bg:#f0f4f8;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Malgun Gothic','맑은 고딕',sans-serif;background:var(--bg);color:#222;}}
mark{{background:#fff176;color:#333;border-radius:2px;padding:0 2px;}}
.update-bar{{background:#1a5c2a;color:#fff;text-align:center;padding:10px;font-size:13px;letter-spacing:0.3px;}}
.update-bar strong{{font-weight:700;}}
.update-bar .next{{opacity:.8;margin-left:16px;font-size:12px;}}
.header{{background:linear-gradient(135deg,#0e2a45,#1a5c9a);color:#fff;padding:32px 20px 26px;text-align:center;}}
.header h1{{font-size:22px;margin-bottom:6px;}}
.sub{{opacity:.75;font-size:13px;margin-bottom:6px;}}
.kw-filter{{display:inline-flex;gap:8px;margin:10px 0 18px;flex-wrap:wrap;justify-content:center;}}
.kw-filter span{{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.4);border-radius:20px;padding:4px 14px;font-size:13px;font-weight:700;}}
.stats{{display:flex;justify-content:center;gap:14px;flex-wrap:wrap;}}
.stat{{background:rgba(255,255,255,.15);border-radius:10px;padding:11px 26px;text-align:center;}}
.stat .num{{font-size:28px;font-weight:800;}}.stat .lbl{{font-size:11px;opacity:.75;margin-top:3px;}}
.tabs{{display:flex;background:#fff;border-bottom:2px solid #dce3ea;position:sticky;top:0;z-index:20;box-shadow:0 2px 8px rgba(0,0,0,.06);}}
.tbtn{{flex:1;padding:13px 4px;border:none;background:none;font-size:14px;font-family:inherit;color:#666;cursor:pointer;border-bottom:3px solid transparent;transition:.15s;}}
.tbtn:hover{{background:#f5f9fe;color:var(--a);}}.tbtn.on{{color:var(--a);border-bottom-color:var(--a);font-weight:700;background:#eef5fb;}}
.pane{{display:none;padding:22px 18px;max-width:1280px;margin:0 auto;}}.pane.on{{display:block;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px;}}
.card{{background:#fff;border-radius:12px;box-shadow:0 3px 14px rgba(0,0,0,.08);overflow:hidden;display:flex;flex-direction:column;transition:.2s;}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 22px rgba(0,0,0,.13);}}
.cimg{{height:170px;background:#f3f6fa;display:flex;align-items:center;justify-content:center;overflow:hidden;}}
.cimg img{{width:100%;height:100%;object-fit:contain;padding:8px;}}
.noimg{{display:flex;align-items:center;justify-content:center;color:#bbb;font-size:13px;width:100%;height:100%;}}
.cbody{{padding:14px;display:flex;flex-direction:column;gap:9px;flex:1;}}
.ctop{{display:flex;justify-content:space-between;align-items:center;}}
.badge{{font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px;}}
.b-dom{{background:#dbeafe;color:#1e40af;}}.b-for{{background:#fce7f3;color:#9d174d;}}
.date{{font-size:11px;color:#999;}}
h3{{font-size:14px;font-weight:700;line-height:1.45;}}
h3 a{{color:var(--p);text-decoration:none;}}h3 a:hover{{text-decoration:underline;color:var(--a);}}
.kwrow{{display:flex;gap:5px;flex-wrap:wrap;}}
.kw{{background:#fff9c4;color:#7c6a00;font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px;border:1px solid #f5d800;}}
.info{{width:100%;border-collapse:collapse;font-size:12px;}}
.info th{{width:60px;color:#777;font-weight:600;padding:3px 0;vertical-align:top;}}.info td{{color:#333;padding:3px 0;}}
.rtype{{font-weight:600;color:var(--w);}}
.hbox{{background:#fff8f1;border-left:3px solid #f59e0b;border-radius:4px;padding:8px 10px;}}
.hlabel{{font-size:11px;font-weight:700;color:#b45309;margin-bottom:4px;}}
.htext{{font-size:12px;color:#444;line-height:1.6;max-height:78px;overflow-y:auto;}}
.dbtn{{display:inline-block;font-size:12px;color:var(--a);font-weight:600;text-decoration:none;margin-top:auto;}}
.dbtn:hover{{text-decoration:underline;}}
.empty{{text-align:center;padding:48px;color:#aaa;font-size:15px;}}
footer{{text-align:center;padding:24px;color:#bbb;font-size:11px;}}
</style>
</head>
<body>
<div class="update-bar">
  ✅ <strong>마지막 업데이트: {today}</strong>
  <span class="next">🔄 다음 업데이트 예정: {next_monday} (매주 월요일 자동 갱신)</span>
</div>
<div class="header">
  <h1>🔔 제품안전 리콜 정보</h1>
  <p class="sub">조회 기간: {start_fmt} ~ {end_fmt}</p>
  <div class="kw-filter">{"".join(f'<span>🔍 {kw}</span>' for kw in FILTER_KEYWORDS) if FILTER_KEYWORDS else "<span>전체 표시</span>"}</div>
  <div class="stats">
    <div class="stat"><div class="num">{total}</div><div class="lbl">필터 결과</div></div>
    <div class="stat"><div class="num">{len(domestic)}</div><div class="lbl">🇰🇷 국내</div></div>
    <div class="stat"><div class="num">{len(overseas)}</div><div class="lbl">🌍 국외</div></div>
  </div>
</div>
<div class="tabs">
  <button class="tbtn on" onclick="sw(this,'all')">전체 ({total})</button>
  <button class="tbtn"    onclick="sw(this,'dom')">🇰🇷 국내 ({len(domestic)})</button>
  <button class="tbtn"    onclick="sw(this,'for')">🌍 국외 ({len(overseas)})</button>
</div>
<div id="p-all" class="pane on"><div class="grid">{all_c or '<p class="empty">해당 키워드 리콜 없음</p>'}</div></div>
<div id="p-dom" class="pane"><div class="grid">{dom_c}</div></div>
<div id="p-for" class="pane"><div class="grid">{for_c}</div></div>
<footer>출처: 제품안전정보센터 (www.safetykorea.kr) — 국가기술표준원 | 키워드: {kw_str}</footer>
<script>
function sw(btn,id){{
  document.querySelectorAll('.tbtn').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('on'));
  btn.classList.add('on'); document.getElementById('p-'+id).classList.add('on');
}}
</script>
</body></html>"""


def main():
    end_dt    = datetime.now()
    start_dt  = end_dt - timedelta(days=DAYS_BACK)
    start_str = start_dt.strftime("%Y%m%d")
    end_str   = end_dt.strftime("%Y%m%d")
    start_fmt = start_dt.strftime("%Y.%m.%d")
    end_fmt   = end_dt.strftime("%Y.%m.%d")
    kw_display = f"[{', '.join(FILTER_KEYWORDS)}]" if FILTER_KEYWORDS else "[전체]"

    print("="*55)
    print("  제품안전정보센터 리콜 수집기")
    print("="*55)
    print(f"\n  기간  : {start_fmt} ~ {end_fmt} ({DAYS_BACK}일)")
    print(f"  키워드: {kw_display}")
    print(f"  모드  : {'자동(스케줄러)' if AUTO_MODE else '수동'}\n")

    dom_list  = collect_list(BASE+"/recall/recallBoard",  "국내", start_str, end_str)
    for_list  = collect_list(BASE+"/recall/fRecallBoard", "국외", start_str, end_str)
    print()
    dom_items = enrich_and_filter(dom_list, BASE+"/recall/ajax/recallBoard",  "국내")
    for_items = enrich_and_filter(for_list, BASE+"/recall/ajax/fRecallBoard", "국외")

    total = len(dom_items)+len(for_items)
    print(f"\n✅ 최종: 국내 {len(dom_items)}건 + 국외 {len(for_items)}건 = {total}건 {kw_display}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # index.html 로 저장 → GitHub Pages URL이 항상 동일하게 유지됨
    fpath = os.path.join(OUTPUT_DIR, "index.html")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(generate_html(dom_items, for_items, start_fmt, end_fmt))

    abs_path = os.path.abspath(fpath)
    print(f"💾 저장: {abs_path}")

    if not AUTO_MODE:
        print("🌐 브라우저 열기...\n")
        webbrowser.open("file:///"+abs_path.replace("\\","/"))
        input("완료! [Enter]를 누르면 종료...")
    else:
        print("✔ 자동 모드 완료")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback; traceback.print_exc()
        if not AUTO_MODE: input("\n[Enter]를 누르면 종료...")
        sys.exit(1)
