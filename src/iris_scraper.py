from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

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
    바로_가기_링크: str = BASE_URL
    공고상태: str = ""
    공모유형: str = ""
    수집일시_UTC: str = ""
    source_key: str = ""

    def to_csv_row(self) -> dict[str, str]:
        return {
            "소관부처": self.소관부처,
            "전문기관": self.전문기관,
            "공고번호": self.공고번호,
            "공고명": self.공고명,
            "공고일자": self.공고일자,
            "접수기간": self.접수기간,
            "사업담당자 연락처": self.사업담당자_연락처,
            "접수 개시 여부": self.접수_개시_여부,
            "바로 가기 링크": self.바로_가기_링크,
            "공고상태": self.공고상태,
            "공모유형": self.공모유형,
            "수집일시_UTC": self.수집일시_UTC,
            "source_key": self.source_key,
        }


def clean_text(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("？", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fetch_page(page: int = 1, timeout: int = 30) -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    # IRIS currently exposes page 1 as server-rendered text. For later pages, try common paging params.
    candidates = [BASE_URL]
    if page > 1:
        params_list = [
            {"pageIndex": page},
            {"pageNo": page},
            {"curPage": page},
            {"page": page},
        ]
        candidates = [BASE_URL + "?" + urlencode(p) for p in params_list]
    last_error = None
    for url in candidates:
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            if "사업공고" in r.text or "공고번호" in r.text:
                return r.text
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError(f"failed to fetch IRIS page {page}: {last_error}")
    raise RuntimeError(f"failed to fetch IRIS page {page}: page did not contain expected text")


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [clean_text(x) for x in text.splitlines()]
    return [x for x in lines if x]


def parse_total_pages(lines: list[str]) -> int:
    joined = " ".join(lines)
    m = re.search(r"현재\s*페이지\s*\d+\s*/\s*(\d+)", joined)
    if m:
        return int(m.group(1))
    return 1


def make_key(no: str, title: str, date: str) -> str:
    raw = "|".join([clean_text(no), clean_text(title), clean_text(date)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_list_html(html: str, page_url: str = BASE_URL) -> list[Announcement]:
    lines = html_to_lines(html)
    out: list[Announcement] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Pattern seen on IRIS: department > agency, title, meta line containing 공고번호/공고일자/공고상태/공모유형.
    for i, line in enumerate(lines):
        if " > " not in line:
            continue
        if any(skip in line for skip in ["관련부처", "전문기관 홈페이지", "IRIS", "Home"]):
            continue
        left, right = [clean_text(x) for x in line.split(" > ", 1)]
        if not left or not right or len(line) > 120:
            continue

        # Search the next few lines for title and metadata.
        title = ""
        meta = ""
        status_line = ""
        for j in range(i + 1, min(i + 8, len(lines))):
            candidate = lines[j]
            if "공고번호" in candidate and "공고일자" in candidate:
                meta = candidate
                break
            if not title and candidate not in {"접수중", "접수예정", "마감"} and "공고번호" not in candidate:
                title = candidate
        for j in range(i + 1, min(i + 10, len(lines))):
            if lines[j] in {"접수중", "접수예정", "마감"}:
                status_line = lines[j]
                break
        if not title or not meta:
            continue

        no = re.search(r"공고번호\s*:\s*(.*?)\s*공고일자\s*:", meta)
        date = re.search(r"공고일자\s*:\s*(\d{4}-\d{2}-\d{2})", meta)
        state = re.search(r"공고상태\s*:\s*(.*?)\s*공모유형\s*:", meta)
        typ = re.search(r"공모유형\s*:\s*(.*)$", meta)

        ann = Announcement(
            소관부처=left,
            전문기관=right,
            공고번호=clean_text(no.group(1)) if no else "",
            공고명=clean_text(title),
            공고일자=clean_text(date.group(1)) if date else "",
            접수기간="",
            사업담당자_연락처="",
            접수_개시_여부="Y" if (status_line == "접수중" or "접수중" in meta) else ("N" if status_line in {"접수예정", "마감"} else ""),
            바로_가기_링크=page_url,
            공고상태=clean_text(state.group(1)) if state else status_line,
            공모유형=clean_text(typ.group(1)) if typ else "",
            수집일시_UTC=now,
        )
        ann.source_key = make_key(ann.공고번호, ann.공고명, ann.공고일자)
        out.append(ann)

    # Deduplicate within parsed page.
    seen = set()
    deduped = []
    for ann in out:
        if ann.source_key not in seen:
            seen.add(ann.source_key)
            deduped.append(ann)
    return deduped


def read_existing_keys(csv_path: Path) -> set[str]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        keys = set()
        for row in reader:
            key = row.get("source_key") or make_key(row.get("공고번호", ""), row.get("공고명", ""), row.get("공고일자", ""))
            if key:
                keys.add(key)
        return keys


def append_csv(csv_path: Path, records: Iterable[Announcement]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_existing_keys(csv_path)
    new_rows = []
    for rec in records:
        if rec.source_key not in existing:
            new_rows.append(rec.to_csv_row())
            existing.add(rec.source_key)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        for row in new_rows:
            writer.writerow(row)
    return len(new_rows)


def scrape(max_pages: int = 1, save_debug: bool = True) -> list[Announcement]:
    all_records: list[Announcement] = []
    first_html = fetch_page(1)
    if save_debug:
        Path("debug_iris_page1.html").write_text(first_html, encoding="utf-8")
    first_lines = html_to_lines(first_html)
    pages = min(max_pages, parse_total_pages(first_lines))
    if pages < 1:
        pages = 1
    for page in range(1, pages + 1):
        html = first_html if page == 1 else fetch_page(page)
        if save_debug and page != 1:
            Path(f"debug_iris_page{page}.html").write_text(html, encoding="utf-8")
        records = parse_list_html(html, BASE_URL if page == 1 else f"{BASE_URL}?pageIndex={page}")
        print(f"[info] page {page}: parsed {len(records)} records")
        all_records.extend(records)
    # Global dedupe.
    by_key = {}
    for r in all_records:
        by_key.setdefault(r.source_key, r)
    return list(by_key.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/iris_announcements.csv")
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("IRIS_MAX_PAGES", "1")))
    parser.add_argument("--allow-empty", action="store_true", help="Do not fail when zero records are scraped.")
    args = parser.parse_args(argv)

    try:
        records = scrape(max_pages=args.max_pages)
        appended = append_csv(Path(args.csv), records)
        print(f"[result] scraped={len(records)} appended={appended} csv={args.csv}")
        if Path(args.csv).exists():
            print(f"[result] csv_size={Path(args.csv).stat().st_size} bytes")
        if len(records) == 0 and not args.allow_empty:
            print("[fatal] 0 records scraped. See debug_iris_page1.html.", file=sys.stderr)
            return 2
        return 0
    except Exception as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
