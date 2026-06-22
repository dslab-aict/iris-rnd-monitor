from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.iris.go.kr"
LIST_URL = f"{BASE_URL}/contents/retrieveBsnsAncmBtinSituListView.do"
KST = timezone(timedelta(hours=9))

HEADERS = [
    "소관부처",
    "전문기관",
    "공고번호",
    "공고명",
    "공고일자",
    "접수기간",
    "사업담당자 연락처",
    "접수 개시 여부",
    "바로 가기 링크",
    "수집일시",
]

STATUS_WORDS = ("접수중", "접수예정", "마감", "공고접수중", "공고접수예정", "공고마감")


@dataclass
class Announcement:
    소관부처: str = ""
    전문기관: str = ""
    공고번호: str = ""
    공고명: str = ""
    공고일자: str = ""
    접수기간: str = ""
    사업담당자_연락처: str = ""
    접수_개시_여부: str = ""
    바로_가기_링크: str = ""
    수집일시: str = ""

    def row(self) -> dict[str, str]:
        data = asdict(self)
        return {
            "소관부처": data["소관부처"],
            "전문기관": data["전문기관"],
            "공고번호": data["공고번호"],
            "공고명": data["공고명"],
            "공고일자": data["공고일자"],
            "접수기간": data["접수기간"],
            "사업담당자 연락처": data["사업담당자_연락처"],
            "접수 개시 여부": data["접수_개시_여부"],
            "바로 가기 링크": data["바로_가기_링크"],
            "수집일시": data["수집일시"],
        }

    def dedupe_key(self) -> str:
        raw = "|".join([self.공고번호.strip(), self.공고명.strip(), self.공고일자.strip()])
        if raw == "||":
            raw = self.바로_가기_링크 or repr(self.row())
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\xa0", " ").replace("？", "-").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def parse_meta_line(line: str) -> tuple[str, str, str]:
    text = clean(line)
    ann_no = ""
    ann_date = ""
    status = ""
    m = re.search(r"공고번호\s*[:：]\s*(.*?)\s*공고일자\s*[:：]", text)
    if m:
        ann_no = clean(m.group(1))
    m = re.search(r"공고일자\s*[:：]\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        ann_date = clean(m.group(1))
    m = re.search(r"공고상태\s*[:：]\s*([^\s]+)", text)
    if m:
        status = clean(m.group(1)).replace("공고", "")
    return ann_no, ann_date, status


def parse_announcements_from_html(html: str, source_url: str = LIST_URL) -> list[Announcement]:
    soup = BeautifulSoup(html, "lxml")

    # Remove large navigation/footer chunks where possible, but keep text fallback resilient.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = [clean(x) for x in text.splitlines()]
    lines = [x for x in lines if x]

    records: list[Announcement] = []
    for idx, line in enumerate(lines):
        if "공고번호" not in line or "공고일자" not in line:
            continue
        ann_no, ann_date, status = parse_meta_line(line)
        if not ann_no:
            continue

        title = ""
        ministry = ""
        agency = ""
        for prev in reversed(lines[max(0, idx - 10):idx]):
            if ">" in prev and not agency:
                left, right = prev.split(">", 1)
                ministry = clean(left.lstrip("* "))
                agency = clean(right)
                continue
            if not title:
                banned = {"접수중", "접수예정", "마감", "검색", "사업공고"}
                if prev not in banned and "전체 " not in prev and "현재 페이지" not in prev and ">" not in prev:
                    title = clean(prev.lstrip("#* "))
        if not status:
            for nxt in lines[idx + 1:idx + 5]:
                if nxt in STATUS_WORDS:
                    status = nxt.replace("공고", "")
                    break
        records.append(
            Announcement(
                소관부처=ministry,
                전문기관=agency,
                공고번호=ann_no,
                공고명=title,
                공고일자=ann_date,
                접수_개시_여부=status,
                바로_가기_링크=source_url,
            )
        )

    # Deduplicate within page.
    unique: list[Announcement] = []
    seen: set[str] = set()
    for rec in records:
        key = rec.dedupe_key()
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    return unique


def extract_detail_fields(text: str) -> tuple[str, str]:
    t = clean(text)
    period_patterns = [
        r"(?:접수|신청)\s*기간\s*[:：]?\s*(\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}.{0,120}?)(?:\s{2,}|사업|담당|문의|접수방법|신청방법|$)",
        r"공고\s*및\s*접수\s*기간\s*[:：]?\s*(\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}.{0,120}?)(?:\s{2,}|사업|담당|문의|$)",
    ]
    contact_patterns = [
        r"(?:사업\s*)?담당자.{0,50}?((?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4})(?:\s*[,/ ]\s*(?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4}))*)",
        r"문의처.{0,80}?((?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4})(?:\s*[,/ ]\s*(?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4}))*)",
        r"\b(0\d{1,2}-\d{3,4}-\d{4})\b",
    ]
    period = ""
    contact = ""
    for pat in period_patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            period = clean(m.group(1))
            break
    for pat in contact_patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            contact = clean(m.group(1))
            break
    return period, contact


class IrisScraper:
    def __init__(self, max_pages: int = 7, headless: bool = True, sleep_sec: float = 0.5):
        self.max_pages = max_pages
        self.headless = headless
        self.sleep_sec = sleep_sec

    def scrape(self) -> list[Announcement]:
        # Static HTML is sufficient for the core list fields and is more stable in CI.
        records = self._scrape_static_html_pages()
        if records:
            return records
        print("[warn] Static scrape returned 0 records. Trying Playwright fallback.", file=sys.stderr)
        return self._scrape_with_playwright()

    def _scrape_static_html_pages(self) -> list[Announcement]:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; IRIS-RND-Scraper/2.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        all_records: list[Announcement] = []
        seen: set[str] = set()
        now = datetime.now(KST).isoformat(timespec="seconds")
        for page_no in range(1, self.max_pages + 1):
            params = {"pageIndex": str(page_no)} if page_no > 1 else None
            response = session.get(LIST_URL, params=params, timeout=30)
            response.raise_for_status()
            records = parse_announcements_from_html(response.text, response.url)
            print(f"[info] static page {page_no}: parsed {len(records)} records")
            if page_no == 1:
                Path("debug_iris_page1.html").write_text(response.text, encoding="utf-8")
            if not records:
                break
            new_this_page = 0
            for rec in records:
                rec.수집일시 = now
                key = rec.dedupe_key()
                if key in seen:
                    continue
                seen.add(key)
                all_records.append(rec)
                new_this_page += 1
            if new_this_page == 0:
                break
        return all_records

    def _scrape_with_playwright(self) -> list[Announcement]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            print(f"[error] Playwright unavailable: {exc}", file=sys.stderr)
            return []

        records: list[Announcement] = []
        seen: set[str] = set()
        now = datetime.now(KST).isoformat(timespec="seconds")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page(locale="ko-KR", timezone_id="Asia/Seoul")
                page.goto(LIST_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                html = page.content()
                Path("debug_iris_playwright.html").write_text(html, encoding="utf-8")
                parsed = parse_announcements_from_html(html, page.url)
                print(f"[info] playwright page 1: parsed {len(parsed)} records")
                for rec in parsed:
                    rec.수집일시 = now
                    self._try_enrich_from_detail(page, rec)
                    key = rec.dedupe_key()
                    if key not in seen:
                        seen.add(key)
                        records.append(rec)
                browser.close()
        except Exception as exc:
            print(f"[error] Playwright fallback failed: {exc}", file=sys.stderr)
        return records

    def _try_enrich_from_detail(self, page, rec: Announcement) -> None:
        original_url = page.url
        try:
            page.get_by_text(rec.공고명, exact=True).first.click(timeout=4000)
            page.wait_for_timeout(2000)
            body = page.locator("body").inner_text(timeout=10000)
            period, contact = extract_detail_fields(body)
            if period:
                rec.접수기간 = period
            if contact:
                rec.사업담당자_연락처 = contact
            rec.바로_가기_링크 = page.url or original_url
            if page.url != original_url:
                page.go_back(wait_until="domcontentloaded", timeout=10000)
        except Exception as exc:
            print(f"[warn] detail enrich failed: {rec.공고번호} {exc}", file=sys.stderr)
            try:
                if page.url != original_url:
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
            except Exception:
                pass


def load_existing_keys(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    keys: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rec = Announcement(
                공고번호=row.get("공고번호", ""),
                공고명=row.get("공고명", ""),
                공고일자=row.get("공고일자", ""),
                바로_가기_링크=row.get("바로 가기 링크", ""),
            )
            keys.add(rec.dedupe_key())
    return keys


def append_new_records(csv_path: Path, records: Iterable[Announcement]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing_keys(csv_path)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    count = 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        if not file_exists:
            writer.writeheader()
        for rec in records:
            key = rec.dedupe_key()
            if key in existing:
                continue
            writer.writerow(rec.row())
            existing.add(key)
            count += 1
    return count


def main() -> int:
    output = Path(os.getenv("IRIS_OUTPUT_CSV", "data/iris_announcements.csv"))
    max_pages = int(os.getenv("IRIS_MAX_PAGES", "7"))
    headless = os.getenv("IRIS_HEADLESS", "true").lower() not in {"0", "false", "no"}
    fail_on_zero = os.getenv("IRIS_FAIL_ON_ZERO", "true").lower() not in {"0", "false", "no"}

    scraper = IrisScraper(max_pages=max_pages, headless=headless)
    records = scraper.scrape()
    added = append_new_records(output, records)

    print(f"[result] scraped={len(records)} appended={added} csv={output}")
    if output.exists():
        print(f"[result] csv_size={output.stat().st_size} bytes")
    if records[:3]:
        print("[sample]")
        for rec in records[:3]:
            print(f"- {rec.공고일자} | {rec.공고번호} | {rec.공고명}")
    if fail_on_zero and len(records) == 0:
        print("[fatal] 0 records scraped. Check debug_iris_page1.html or site accessibility.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
