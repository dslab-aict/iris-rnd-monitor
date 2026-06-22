from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.iris.go.kr"
LIST_URL = f"{BASE_URL}/contents/retrieveBsnsAncmBtinSituListView.do"
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
KST = timezone(timedelta(hours=9))


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
        d = asdict(self)
        return {
            "소관부처": d["소관부처"],
            "전문기관": d["전문기관"],
            "공고번호": d["공고번호"],
            "공고명": d["공고명"],
            "공고일자": d["공고일자"],
            "접수기간": d["접수기간"],
            "사업담당자 연락처": d["사업담당자_연락처"],
            "접수 개시 여부": d["접수_개시_여부"],
            "바로 가기 링크": d["바로_가기_링크"],
            "수집일시": d["수집일시"],
        }

    def dedupe_key(self) -> str:
        raw = "|".join([self.공고번호.strip(), self.공고명.strip(), self.공고일자.strip()])
        if raw == "||":
            raw = self.바로_가기_링크 or repr(self.row())
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("？", "-").replace("–", "-").replace("~", "~")
    return re.sub(r"\s+", " ", text).strip()


def extract_between(text: str, start: str, stop_words: list[str]) -> str:
    pattern = re.escape(start) + r"\s*:?\s*(.*?)\s*(?:" + "|".join(map(re.escape, stop_words)) + r")"
    m = re.search(pattern, text)
    return clean(m.group(1)) if m else ""


def parse_announcements_from_html(html: str, source_url: str = LIST_URL) -> list[Announcement]:
    """Parse the server-rendered list page.

    IRIS currently exposes the first page list in static HTML. This parser is
    intentionally text-based because the public page can change class names.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [clean(x) for x in text.splitlines()]
    lines = [x for x in lines if x]

    records: list[Announcement] = []
    for i, line in enumerate(lines):
        if "공고번호" not in line or "공고일자" not in line:
            continue

        # Find title: nearest preceding meaningful line that is not agency/status.
        title = ""
        agency_line = ""
        for j in range(i - 1, max(-1, i - 8), -1):
            prev = lines[j]
            if not title and not (">" in prev or prev in {"접수중", "접수예정", "마감"} or prev.startswith("####")):
                title = prev
            if ">" in prev:
                agency_line = prev
                break

        ministry, agency = "", ""
        if ">" in agency_line:
            parts = [clean(p) for p in agency_line.split(">", 1)]
            ministry, agency = parts[0], parts[1]

        ann_no = extract_between(line, "공고번호", ["공고일자", "공고상태", "공모유형"])
        date = extract_between(line, "공고일자", ["공고상태", "공모유형"])
        status = extract_between(line, "공고상태", ["공모유형"])
        if not status:
            for nxt in lines[i + 1 : i + 4]:
                if nxt in {"접수중", "접수예정", "마감"}:
                    status = nxt
                    break

        if title and ann_no:
            records.append(
                Announcement(
                    소관부처=ministry,
                    전문기관=agency,
                    공고번호=ann_no,
                    공고명=title,
                    공고일자=date,
                    접수_개시_여부=status,
                    바로_가기_링크=source_url,
                )
            )
    return records


def extract_detail_fields(text: str) -> tuple[str, str]:
    """Return (application_period, contact)."""
    t = clean(text)
    period_patterns = [
        r"접수\s*기간\s*[:：]?\s*([^\n]+?)(?:\s{2,}| 사업| 담당| 문의| 접수방법|$)",
        r"신청\s*기간\s*[:：]?\s*([^\n]+?)(?:\s{2,}| 사업| 담당| 문의| 신청방법|$)",
        r"공고\s*및\s*접수\s*기간\s*[:：]?\s*([^\n]+?)(?:\s{2,}| 사업| 담당| 문의|$)",
        r"(\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}[^\n]{0,80}?(?:까지|\d{1,2}:\d{2}))",
    ]
    contact_patterns = [
        r"(?:사업\s*)?담당자[^\n]{0,30}?((?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4})(?:\s*[,/ ]\s*(?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4}))*)",
        r"문의처[^\n]{0,60}?((?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4})(?:\s*[,/ ]\s*(?:0\d{1,2}[-)]?\s?\d{3,4}[- ]?\d{4}|\d{2,4}-\d{3,4}-\d{4}))*)",
        r"(\b0\d{1,2}-\d{3,4}-\d{4}\b)",
    ]
    period = ""
    contact = ""
    for p in period_patterns:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            period = clean(m.group(1))
            break
    for p in contact_patterns:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            contact = clean(m.group(1))
            break
    return period, contact


class IrisScraper:
    def __init__(self, max_pages: int = 10, headless: bool = True, sleep_sec: float = 0.6):
        self.max_pages = max_pages
        self.headless = headless
        self.sleep_sec = sleep_sec

    def scrape(self) -> list[Announcement]:
        try:
            return self._scrape_with_playwright()
        except Exception as exc:  # pragma: no cover - runtime fallback
            print(f"[warn] Playwright scraping failed; falling back to static HTML: {exc}", file=sys.stderr)
            try:
                return self._scrape_static_html()
            except Exception as fallback_exc:
                # Do not fail the whole scheduled job because of a temporary
                # network/DNS/site outage. main() will still create the CSV
                # header if needed and GitHub Actions will finish successfully.
                print(f"[error] Static HTML fallback also failed: {fallback_exc}", file=sys.stderr)
                return []

    def _scrape_static_html(self) -> list[Announcement]:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0 IRIS-RND-Scraper/1.0"})
        r = sess.get(LIST_URL, timeout=30)
        r.raise_for_status()
        records = parse_announcements_from_html(r.text, LIST_URL)
        now = datetime.now(KST).isoformat(timespec="seconds")
        for rec in records:
            rec.수집일시 = now
        return records

    def _scrape_with_playwright(self) -> list[Announcement]:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

        found: list[Announcement] = []
        seen_keys: set[str] = set()
        now = datetime.now(KST).isoformat(timespec="seconds")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(locale="ko-KR", timezone_id="Asia/Seoul")
            page.goto(LIST_URL, wait_until="networkidle", timeout=45000)

            for page_no in range(1, self.max_pages + 1):
                page.wait_for_load_state("networkidle", timeout=30000)
                html = page.content()
                records = parse_announcements_from_html(html, page.url)
                if not records:
                    break

                for rec in records:
                    rec.수집일시 = now
                    key = rec.dedupe_key()
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    self._enrich_record_from_detail(page, rec)
                    found.append(rec)
                    time.sleep(self.sleep_sec)

                if page_no >= self.max_pages:
                    break
                if not self._go_next_page(page, page_no + 1):
                    break

            browser.close()
        return found

    def _enrich_record_from_detail(self, page, rec: Announcement) -> None:
        original_url = page.url
        try:
            locator = page.get_by_text(rec.공고명, exact=True).first
            locator.click(timeout=5000)
            page.wait_for_load_state("networkidle", timeout=15000)
            # Some IRIS pages use modal/panel updates without navigation.
            detail_text = page.locator("body").inner_text(timeout=10000)
            period, contact = extract_detail_fields(detail_text)
            if period:
                rec.접수기간 = period
            if contact:
                rec.사업담당자_연락처 = contact
            rec.바로_가기_링크 = page.url or original_url
            if page.url != original_url:
                page.go_back(wait_until="networkidle", timeout=15000)
            else:
                # Try to close modal if one opened; harmless when absent.
                for label in ["닫기", "목록"]:
                    try:
                        page.get_by_text(label, exact=True).first.click(timeout=1000)
                        page.wait_for_load_state("networkidle", timeout=5000)
                        break
                    except Exception:
                        pass
        except Exception as exc:
            print(f"[warn] Could not open detail for {rec.공고번호} / {rec.공고명}: {exc}", file=sys.stderr)
            try:
                if page.url != original_url:
                    page.go_back(wait_until="networkidle", timeout=15000)
            except Exception:
                pass

    def _go_next_page(self, page, next_no: int) -> bool:
        # Prefer visible numeric pagination. Fall back to common query params.
        for candidate in [str(next_no), "다음", ">"]:
            try:
                loc = page.get_by_text(candidate, exact=True).last
                if loc.count() > 0:
                    loc.click(timeout=4000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    return True
            except Exception:
                pass
        try:
            page.goto(f"{LIST_URL}?pageIndex={next_no}", wait_until="networkidle", timeout=20000)
            return True
        except Exception:
            return False


def load_existing_keys(csv_path: Path) -> set[str]:
    keys: set[str] = set()
    if not csv_path.exists():
        return keys
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
    out = Path(os.getenv("IRIS_OUTPUT_CSV", "data/iris_announcements.csv"))
    max_pages = int(os.getenv("IRIS_MAX_PAGES", "10"))
    headless = os.getenv("IRIS_HEADLESS", "true").lower() not in {"0", "false", "no"}
    scraper = IrisScraper(max_pages=max_pages, headless=headless)
    records = scraper.scrape()
    added = append_new_records(out, records)
    print(f"Scraped {len(records)} records; appended {added} new records to {out}")
    return 0
