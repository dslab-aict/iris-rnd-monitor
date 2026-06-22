from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do"

CSV_FIELDS = [
    "소관부처",
    "전문기관",
    "공고번호",
    "공고명",
    "공고일자",
    "접수기간",
    "사업담당자 연락처",
    "접수 개시 여부",
    "바로 가기 링크",
    "공고상태",
    "공모유형",
    "상세본문요약",
    "수집일시_UTC",
    "source_key",
]


@dataclass(frozen=True)
class Announcement:
    ministry: str
    agency: str
    notice_no: str
    title: str
    notice_date: str
    reception_period: str = ""
    contact: str = ""
    reception_started: str = ""
    link: str = BASE_URL
    status: str = ""
    competition_type: str = ""
    detail_summary: str = ""
    collected_at_utc: str = ""
    source_key: str = ""

    def to_row(self) -> dict[str, str]:
        return {
            "소관부처": self.ministry,
            "전문기관": self.agency,
            "공고번호": self.notice_no,
            "공고명": self.title,
            "공고일자": self.notice_date,
            "접수기간": self.reception_period,
            "사업담당자 연락처": self.contact,
            "접수 개시 여부": self.reception_started,
            "바로 가기 링크": self.link,
            "공고상태": self.status,
            "공모유형": self.competition_type,
            "상세본문요약": self.detail_summary,
            "수집일시_UTC": self.collected_at_utc,
            "source_key": self.source_key,
        }


def clean_text(value: str) -> str:
    value = value or ""
    value = value.replace("\u00a0", " ")
    value = value.replace("？", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def make_key(notice_no: str, title: str, notice_date: str) -> str:
    raw = "|".join([clean_text(notice_no), clean_text(title), clean_text(notice_date)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_page_url(page: int) -> str:
    if page <= 1:
        return BASE_URL
    return BASE_URL + "?" + urlencode({"pageIndex": page})


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [clean_text(x) for x in soup.get_text("\n").splitlines()]
    return [x for x in lines if x]


def extract_total_pages(html: str) -> int:
    text = "\n".join(html_to_lines(html))
    m = re.search(r"현재\s*페이지\s*\d+\s*/\s*(\d+)", text)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"전체\s*[\d,]+\s*건.*?현재\s*페이지\s*\d+\s*/\s*(\d+)", text)
    if m:
        return max(1, int(m.group(1)))
    return 1


def parse_list_records(html: str, page_url: str = BASE_URL) -> list[Announcement]:
    lines = html_to_lines(html)
    text = "\n".join(lines)
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records: list[Announcement] = []

    pattern = re.compile(
        r"(?P<ministry>[^\n<>]{2,60}?)\s*>\s*(?P<agency>[^\n<>]{2,100}?)\n+"
        r"(?P<title>(?:(?!\n\s*공고번호\s*:).)+?)\n+"
        r"공고번호\s*:\s*(?P<notice_no>.*?)\s*공고일자\s*:\s*"
        r"(?P<notice_date>\d{4}-\d{2}-\d{2})\s*공고상태\s*:\s*"
        r"(?P<status>.*?)\s*공모유형\s*:\s*(?P<competition_type>[^\n]+)",
        re.DOTALL,
    )
    bad_prefixes = ("관련부처", "전문기관 홈페이지", "IRIS", "Home", "사업정보", "R&D정보", "소관부처 전체선택", "전문기관 전체선택")

    for m in pattern.finditer(text):
        ministry = clean_text(m.group("ministry"))
        agency = clean_text(m.group("agency"))
        title = clean_text(m.group("title"))
        notice_no = clean_text(m.group("notice_no"))
        notice_date = clean_text(m.group("notice_date"))
        status = clean_text(m.group("status"))
        competition_type = clean_text(m.group("competition_type"))
        if any(ministry.startswith(x) for x in bad_prefixes):
            continue
        if "전체선택" in ministry or "전체선택" in agency:
            continue
        if not notice_no or not title or not notice_date:
            continue
        if len(title) > 350:
            continue
        records.append(
            Announcement(
                ministry=ministry,
                agency=agency,
                notice_no=notice_no,
                title=title,
                notice_date=notice_date,
                reception_started="Y" if "접수중" in status else "N",
                link=page_url,
                status=status,
                competition_type=competition_type,
                collected_at_utc=collected_at,
                source_key=make_key(notice_no, title, notice_date),
            )
        )

    deduped: list[Announcement] = []
    seen: set[str] = set()
    for record in records:
        if record.source_key in seen:
            continue
        seen.add(record.source_key)
        deduped.append(record)
    return deduped


def first_match(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.M)
        if m:
            return clean_text(m.group(1))
    return ""


def parse_detail_fields(html: str) -> dict[str, str]:
    lines = html_to_lines(html)
    text = "\n".join(lines)
    joined = clean_text(" ".join(lines))

    period = first_match([
        r"접수\s*기간\s*[:：]?\s*([^\n]{6,120})",
        r"신청\s*기간\s*[:：]?\s*([^\n]{6,120})",
        r"연구개발계획서\s*접수기간\s*[:：]?\s*([^\n]{6,120})",
        r"공고\s*및\s*접수기간\s*[:：]?\s*([^\n]{6,120})",
    ], text)
    if not period:
        m = re.search(r"(20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}[^\n]{0,80}?(?:까지|마감|18:00|17:00))", text)
        if m:
            period = clean_text(m.group(1))

    phones = sorted(set(re.findall(r"(?:0\d{1,2}-\d{3,4}-\d{4}|\d{4}-\d{4})", joined)))
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", joined)))
    contact = "; ".join(phones + emails)

    # Keep a compact searchable detail text, excluding global menus as much as possible.
    useful = []
    keywords = ("접수", "신청", "담당", "문의", "연락", "공고", "기간", "주관", "전문기관")
    for line in lines:
        if any(k in line for k in keywords):
            if len(line) <= 220 and line not in useful:
                useful.append(line)
    summary = " | ".join(useful[:12])
    return {"period": period, "contact": contact, "summary": summary}



def normalize_iris_detail_link(raw: str, base_url: str = BASE_URL) -> str:
    """Return a canonical IRIS detail URL when ancmId/ancmPrg are available."""
    raw = clean_text(raw)
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    absolute = urljoin("https://www.iris.go.kr", raw)
    parsed = urlparse(absolute)
    qs = parse_qs(parsed.query)
    ancm_id = (qs.get("ancmId") or qs.get("ancm_id") or [""])[0]
    ancm_prg = (qs.get("ancmPrg") or qs.get("ancm_prg") or [""])[0]
    if ancm_id:
        params = {"ancmId": ancm_id}
        if ancm_prg:
            params["ancmPrg"] = ancm_prg
        return "https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?" + urlencode(params)
    return absolute if "retrieveBsnsAncmView.do" in absolute and "?" in absolute else ""


def extract_detail_link_from_html(html: str, current_url: str = "") -> str:
    """Extract the shareable detail link from IRIS detail HTML/scripts."""
    haystacks = [current_url or "", html or ""]
    url_pat = r"(?:https?://www\.iris\.go\.kr)?/contents/retrieveBsnsAncmView\.do\?[^\s'\"<>]+"
    for text in haystacks:
        for m in re.finditer(url_pat, text):
            link = normalize_iris_detail_link(m.group(0))
            if link:
                return link

    combined = "\n".join(haystacks)
    id_patterns = [
        r"ancmId\s*[:=]\s*['\"]?(\d{3,})",
        r"name\s*=\s*['\"]ancmId['\"][^>]*value\s*=\s*['\"]?(\d{3,})",
        r"id\s*=\s*['\"]ancmId['\"][^>]*value\s*=\s*['\"]?(\d{3,})",
        r"['\"]ancmId['\"]\s*,\s*['\"]?(\d{3,})",
    ]
    prg_patterns = [
        r"ancmPrg\s*[:=]\s*['\"]?([A-Za-z0-9_\-]+)",
        r"name\s*=\s*['\"]ancmPrg['\"][^>]*value\s*=\s*['\"]?([A-Za-z0-9_\-]+)",
        r"id\s*=\s*['\"]ancmPrg['\"][^>]*value\s*=\s*['\"]?([A-Za-z0-9_\-]+)",
        r"['\"]ancmPrg['\"]\s*,\s*['\"]?([A-Za-z0-9_\-]+)",
    ]
    ancm_id = ""
    ancm_prg = ""
    for pat in id_patterns:
        m = re.search(pat, combined, flags=re.I)
        if m:
            ancm_id = m.group(1)
            break
    for pat in prg_patterns:
        m = re.search(pat, combined, flags=re.I)
        if m:
            ancm_prg = m.group(1)
            break
    if ancm_id:
        return normalize_iris_detail_link("/contents/retrieveBsnsAncmView.do?" + urlencode({"ancmId": ancm_id, "ancmPrg": ancm_prg or "ancmIng"}))
    return normalize_iris_detail_link(current_url or "")


def fetch_html(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.iris.go.kr/",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def read_existing_keys(csv_path: Path) -> set[str]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        keys: set[str] = set()
        for row in reader:
            key = row.get("source_key") or make_key(row.get("공고번호", ""), row.get("공고명", ""), row.get("공고일자", ""))
            if key:
                keys.add(key)
        return keys


def append_csv(csv_path: Path, records: Iterable[Announcement]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_existing_keys(csv_path)
    new_rows: list[dict[str, str]] = []
    for record in records:
        if record.source_key in existing:
            continue
        new_rows.append(record.to_row())
        existing.add(record.source_key)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def merge_records(base: Announcement, detail_html: str, link: str) -> Announcement:
    fields = parse_detail_fields(detail_html)
    return replace(
        base,
        reception_period=fields["period"],
        contact=fields["contact"],
        detail_summary=fields["summary"],
        link=link or base.link,
    )


def scrape_static_all(max_pages: int, debug_dir: Path) -> tuple[list[Announcement], int]:
    first_html = fetch_html(BASE_URL)
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "debug_iris_static_page1.html").write_text(first_html, encoding="utf-8")
    total_pages = extract_total_pages(first_html)
    if max_pages and max_pages > 0:
        total_pages = min(total_pages, max_pages)
    records = parse_list_records(first_html, BASE_URL)
    print(f"[info] static page=1 parsed={len(records)} total_pages={total_pages}")
    for page_no in range(2, total_pages + 1):
        url = build_page_url(page_no)
        html = fetch_html(url)
        (debug_dir / f"debug_iris_static_page{page_no}.html").write_text(html, encoding="utf-8")
        page_records = parse_list_records(html, url)
        print(f"[info] static page={page_no} parsed={len(page_records)} url={url}")
        records.extend(page_records)
    return dedupe(records), total_pages


def dedupe(records: Iterable[Announcement]) -> list[Announcement]:
    out: list[Announcement] = []
    seen: set[str] = set()
    for record in records:
        if record.source_key in seen:
            continue
        seen.add(record.source_key)
        out.append(record)
    return out


def click_title_js() -> str:
    return r'''
    (title) => {
      const norm = s => (s || '').replace(/\s+/g, ' ').trim();
      const target = norm(title);
      const nodes = Array.from(document.querySelectorAll('a, button, [onclick], li, div, span, p'));
      let best = null;
      for (const node of nodes) {
        const text = norm(node.innerText || node.textContent || '');
        if (!text || !text.includes(target)) continue;
        if (!best || text.length < norm(best.innerText || best.textContent || '').length) best = node;
      }
      if (!best) return {clicked:false, reason:'title_not_found'};
      const clickable = best.closest('a, button, [onclick], li[onclick], div[onclick]') || best;
      clickable.scrollIntoView({block:'center', inline:'center'});
      clickable.click();
      return {clicked:true, tag: clickable.tagName, text: norm(clickable.innerText || clickable.textContent || '').slice(0, 200)};
    }
    '''


def click_page_js() -> str:
    return r'''
    (pageNo) => {
      const want = String(pageNo);
      const candidates = Array.from(document.querySelectorAll('a, button, [onclick], span'));
      for (const el of candidates) {
        const text = (el.innerText || el.textContent || '').replace(/\s+/g, '').trim();
        const label = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
        if (text === want || label === want || label.includes(want + '페이지')) {
          const clickable = el.closest('a, button, [onclick]') || el;
          clickable.scrollIntoView({block:'center', inline:'center'});
          clickable.click();
          return {clicked:true, text, label};
        }
      }
      return {clicked:false, reason:'page_button_not_found'};
    }
    '''



def click_link_share_js() -> str:
    return r"""
    () => {
      const norm = s => (s || '').replace(/\s+/g, ' ').trim();
      const nodes = Array.from(document.querySelectorAll('a, button, [onclick], span, div, input'));
      let target = null;
      for (const node of nodes) {
        const text = norm(node.innerText || node.textContent || node.value || node.getAttribute('title') || node.getAttribute('aria-label') || '');
        if (text.includes('링크공유') || text.includes('링크 공유') || text.includes('URL복사') || text.includes('URL 복사')) {
          target = node.closest('a, button, [onclick]') || node;
          break;
        }
      }
      if (!target) return {clicked:false, reason:'share_button_not_found'};
      target.scrollIntoView({block:'center', inline:'center'});
      target.click();
      return {clicked:true, text:norm(target.innerText || target.textContent || target.value || '').slice(0, 100)};
    }
    """


def find_url_in_text(text: str) -> str:
    text = text or ""
    for m in re.finditer(r"https?://www\.iris\.go\.kr/contents/retrieveBsnsAncmView\.do\?[^\s'\"<>]+", text):
        link = normalize_iris_detail_link(m.group(0))
        if link:
            return link
    return ""


def scrape_playwright_full(max_pages: int, debug_dir: Path, headless: bool = True) -> list[Announcement]:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    debug_dir.mkdir(parents=True, exist_ok=True)
    detailed: list[Announcement] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        first_html = page.content()
        total_pages = extract_total_pages(first_html)
        if max_pages and max_pages > 0:
            total_pages = min(total_pages, max_pages)
        print(f"[info] playwright total_pages={total_pages}")

        for page_no in range(1, total_pages + 1):
            if page_no > 1:
                target_url = build_page_url(page_no)
                page.goto(target_url, wait_until="networkidle", timeout=60000)
                html_after_url = page.content()
                recs_after_url = parse_list_records(html_after_url, page.url)
                # If pageIndex URL did not move the list, try clicking the numbered paginator.
                if not recs_after_url or (page_no > 1 and "현재 페이지 1/" in "\n".join(html_to_lines(html_after_url))):
                    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
                    result = page.evaluate(click_page_js(), page_no)
                    print(f"[info] pagination click page={page_no} result={json.dumps(result, ensure_ascii=False)}")
                    page.wait_for_load_state("networkidle", timeout=15000)

            list_html = page.content()
            (debug_dir / f"debug_iris_list_page{page_no}.html").write_text(list_html, encoding="utf-8")
            list_records = parse_list_records(list_html, page.url)
            print(f"[info] list page={page_no} records={len(list_records)} url={page.url}")

            for idx, record in enumerate(list_records, start=1):
                # Reopen list page before every click, because detail pages can mutate history/state.
                if page_no == 1:
                    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
                else:
                    page.goto(build_page_url(page_no), wait_until="networkidle", timeout=60000)
                    page_html_check = page.content()
                    if not parse_list_records(page_html_check, page.url):
                        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
                        page.evaluate(click_page_js(), page_no)
                        page.wait_for_load_state("networkidle", timeout=15000)

                before_url = page.url
                click_result = page.evaluate(click_title_js(), record.title)
                print(f"[info] detail click page={page_no} item={idx} clicked={click_result.get('clicked')} title={record.title[:60]}")
                if not click_result.get("clicked"):
                    detailed.append(record)
                    continue
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    pass
                time.sleep(0.6)
                detail_html = page.content()
                detail_url = page.url
                # If content did not change meaningfully, still save debug and keep list fields.
                (debug_dir / f"debug_iris_detail_p{page_no}_i{idx}.html").write_text(detail_html, encoding="utf-8")
                share_link = extract_detail_link_from_html(detail_html, detail_url)
                if not share_link:
                    try:
                        share_result = page.evaluate(click_link_share_js())
                        print(f"[info] link share page={page_no} item={idx} result={json.dumps(share_result, ensure_ascii=False)}")
                        time.sleep(0.4)
                        share_html = page.content()
                        share_text = page.locator("body").inner_text(timeout=3000)
                        (debug_dir / f"debug_iris_share_p{page_no}_i{idx}.html").write_text(share_html, encoding="utf-8")
                        share_link = find_url_in_text(share_text) or extract_detail_link_from_html(share_html, detail_url)
                    except Exception as exc:
                        print(f"[warn] link share extraction failed page={page_no} item={idx}: {exc}")
                final_link = share_link or detail_url
                if detail_url == before_url and record.title in "\n".join(html_to_lines(detail_html)) and len(parse_list_records(detail_html, detail_url)) >= len(list_records):
                    detailed.append(replace(record, link=final_link or record.link))
                else:
                    detailed.append(merge_records(record, detail_html, final_link))

        context.close()
        browser.close()
    return dedupe(detailed)


def scrape(max_pages: int, details: bool, debug_dir: Path) -> list[Announcement]:
    if details:
        return scrape_playwright_full(max_pages=max_pages, debug_dir=debug_dir)
    records, _ = scrape_static_all(max_pages=max_pages, debug_dir=debug_dir)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape IRIS R&D announcements into CSV.")
    parser.add_argument("--csv", default="data/iris_announcements.csv", help="CSV output path")
    parser.add_argument("--max-pages", type=int, default=0, help="0 means auto-detect all pages")
    parser.add_argument("--debug-dir", default=".", help="Directory for debug HTML files")
    parser.add_argument("--details", action="store_true", help="Visit every list page and click every announcement detail")
    args = parser.parse_args(argv)

    try:
        records = scrape(args.max_pages, args.details, Path(args.debug_dir))
    except Exception as exc:
        print(f"[fatal] scrape failed: {exc}", file=sys.stderr)
        return 1

    csv_path = Path(args.csv)
    appended = append_csv(csv_path, records)
    size = csv_path.stat().st_size if csv_path.exists() else 0
    with_detail = sum(1 for r in records if r.reception_period or r.contact or r.detail_summary)
    print(f"[result] scraped={len(records)} with_detail={with_detail} appended={appended} csv={csv_path} csv_size={size}")

    if len(records) == 0:
        print("[fatal] 0 records scraped. Open uploaded iris-debug-html artifact.", file=sys.stderr)
        return 2
    if args.details and with_detail == 0:
        print("[fatal] detail mode ran, but no detail fields were captured. Open debug detail HTML artifacts.", file=sys.stderr)
        return 3
    return 0
