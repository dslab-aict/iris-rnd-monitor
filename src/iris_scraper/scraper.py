from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlencode

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
    "수집일시_UTC",
    "source_key",
]

STATUS_WORDS = {"접수중", "접수예정", "마감"}


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
            "수집일시_UTC": self.collected_at_utc,
            "source_key": self.source_key,
        }


def clean_text(value: str) -> str:
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


def fetch_html(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.iris.go.kr/",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def html_to_lines(html: str) -> list[str]:
    # Use Python's built-in parser. Do not require lxml on GitHub runners.
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [clean_text(x) for x in soup.get_text("\n").splitlines()]
    return [x for x in lines if x]


def find_link_for_title(html: str, title: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title_norm = clean_text(title)
    for tag in soup.find_all(["a", "button"]):
        text = clean_text(tag.get_text(" "))
        if not text or title_norm not in text:
            continue
        href = tag.get("href")
        onclick = tag.get("onclick") or ""
        if href and href != "#":
            return urljoin(base_url, href)
        # Preserve JavaScript navigation if that is all IRIS exposes.
        if onclick:
            return base_url + "#onclick=" + re.sub(r"\s+", " ", onclick.strip())
    return base_url


def parse_meta(meta: str) -> tuple[str, str, str, str]:
    notice_no = ""
    notice_date = ""
    status = ""
    competition_type = ""

    m = re.search(r"공고번호\s*:\s*(.*?)\s*공고일자\s*:", meta)
    if m:
        notice_no = clean_text(m.group(1))
    m = re.search(r"공고일자\s*:\s*(\d{4}-\d{2}-\d{2})", meta)
    if m:
        notice_date = clean_text(m.group(1))
    m = re.search(r"공고상태\s*:\s*(.*?)\s*공모유형\s*:", meta)
    if m:
        status = clean_text(m.group(1))
    m = re.search(r"공모유형\s*:\s*(.*)$", meta)
    if m:
        competition_type = clean_text(m.group(1))
    return notice_no, notice_date, status, competition_type


def parse_detail_fields(html: str) -> tuple[str, str]:
    lines = html_to_lines(html)
    joined = "\n".join(lines)

    period = ""
    contact = ""

    patterns_period = [
        r"접수기간\s*[:：]?\s*([^\n]+)",
        r"연구개발계획서\s*접수기간\s*[:：]?\s*([^\n]+)",
        r"신청기간\s*[:：]?\s*([^\n]+)",
    ]
    for pat in patterns_period:
        m = re.search(pat, joined)
        if m:
            period = clean_text(m.group(1))
            break

    # Korean phone numbers, optionally combined with 담당자 nearby.
    phone = re.search(r"(?:\d{2,4}-\d{3,4}-\d{4}|\d{4}-\d{4})", joined)
    if phone:
        contact = phone.group(0)

    return period, contact


def parse_announcements_from_html(html: str, page_url: str = BASE_URL, fetch_details: bool = False) -> list[Announcement]:
    lines = html_to_lines(html)
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records: list[Announcement] = []

    for i, line in enumerate(lines):
        if " > " not in line:
            continue
        if any(x in line for x in ["관련부처", "전문기관 홈페이지", "IRIS", "Home"]):
            continue
        if len(line) > 140:
            continue

        ministry, agency = [clean_text(x) for x in line.split(" > ", 1)]
        if not ministry or not agency:
            continue

        title = ""
        meta = ""
        explicit_status = ""
        for j in range(i + 1, min(i + 12, len(lines))):
            candidate = lines[j]
            if candidate in STATUS_WORDS and not explicit_status:
                explicit_status = candidate
                continue
            if "공고번호" in candidate and "공고일자" in candidate:
                meta = candidate
                break
            if not title and "공고번호" not in candidate and candidate not in STATUS_WORDS:
                title = candidate

        if not title or not meta:
            continue

        notice_no, notice_date, status, competition_type = parse_meta(meta)
        status = status or explicit_status
        reception_started = "Y" if "접수중" in status or explicit_status == "접수중" else "N"
        link = find_link_for_title(html, title, page_url)

        period = ""
        contact = ""
        if fetch_details and link.startswith("http") and link != page_url and "#onclick=" not in link:
            try:
                detail_html = fetch_html(link)
                period, contact = parse_detail_fields(detail_html)
            except Exception as exc:
                print(f"[warn] detail fetch failed: {title}: {exc}", file=sys.stderr)

        key = make_key(notice_no, title, notice_date)
        records.append(
            Announcement(
                ministry=ministry,
                agency=agency,
                notice_no=notice_no,
                title=title,
                notice_date=notice_date,
                reception_period=period,
                contact=contact,
                reception_started=reception_started,
                link=link,
                status=status,
                competition_type=competition_type,
                collected_at_utc=collected_at,
                source_key=key,
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


def read_existing_keys(csv_path: Path) -> set[str]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        keys: set[str] = set()
        for row in reader:
            key = row.get("source_key") or make_key(
                row.get("공고번호", ""), row.get("공고명", ""), row.get("공고일자", "")
            )
            if key:
                keys.add(key)
        return keys


def append_csv(csv_path: Path, records: Iterable[Announcement]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_existing_keys(csv_path)
    new_rows: list[dict[str, str]] = []
    for record in records:
        if record.source_key not in existing:
            new_rows.append(record.to_row())
            existing.add(record.source_key)

    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def scrape(max_pages: int, fetch_details: bool, debug_dir: Path) -> list[Announcement]:
    all_records: list[Announcement] = []
    for page in range(1, max_pages + 1):
        url = build_page_url(page)
        html = fetch_html(url)
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"debug_iris_page{page}.html").write_text(html, encoding="utf-8")
        records = parse_announcements_from_html(html, url, fetch_details=fetch_details)
        print(f"[info] page={page} parsed={len(records)} url={url}")
        all_records.extend(records)
    # global dedupe
    seen: set[str] = set()
    deduped: list[Announcement] = []
    for record in all_records:
        if record.source_key in seen:
            continue
        seen.add(record.source_key)
        deduped.append(record)
    return deduped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape IRIS R&D announcements into CSV.")
    parser.add_argument("--csv", default="data/iris_announcements.csv", help="CSV output path")
    parser.add_argument("--max-pages", type=int, default=1, help="Number of list pages to fetch")
    parser.add_argument("--debug-dir", default=".", help="Directory for debug_iris_page*.html")
    parser.add_argument("--fetch-details", action="store_true", help="Try to fetch detail pages when hrefs are exposed")
    args = parser.parse_args(argv)

    try:
        records = scrape(args.max_pages, args.fetch_details, Path(args.debug_dir))
    except Exception as exc:
        print(f"[fatal] scrape failed: {exc}", file=sys.stderr)
        return 1

    csv_path = Path(args.csv)
    appended = append_csv(csv_path, records)
    size = csv_path.stat().st_size if csv_path.exists() else 0
    print(f"[result] scraped={len(records)} appended={appended} csv={csv_path} csv_size={size}")

    if len(records) == 0:
        print("[fatal] 0 records scraped. Open uploaded debug_iris_page1.html artifact.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
