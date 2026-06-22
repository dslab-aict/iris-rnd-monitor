# IRIS 국가연구개발 사업공고 CSV 스크래퍼

IRIS 사업공고 페이지를 매일 00:00 KST에 수집해 `data/iris_announcements.csv`에 append합니다.

## 수집 필드

- 소관부처
- 전문기관
- 공고번호
- 공고명
- 공고일자
- 접수기간
- 사업담당자 연락처
- 접수 개시 여부
- 바로 가기 링크
- 공고상태
- 공모유형

현재 IRIS 목록 HTML에서 안정적으로 노출되는 값은 소관부처, 전문기관, 공고번호, 공고명, 공고일자, 공고상태, 공모유형입니다. 상세 페이지 고유 URL, 접수기간, 담당자 연락처는 목록 정적 HTML에 없으면 공란으로 저장합니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m iris_scraper --csv data/iris_announcements.csv --max-pages 1
```

## GitHub Actions 실행

1. 이 프로젝트 전체를 GitHub repository에 업로드합니다.
2. `Actions` 탭에서 `IRIS RND Scraper`를 선택합니다.
3. `Run workflow`를 누릅니다.
4. 실행 로그에서 다음을 확인합니다.

```text
[info] page 1: parsed ... records
[result] scraped=... appended=...
--- CSV preview ---
```

## 중복 방지

`공고번호 + 공고명 + 공고일자`를 SHA-256 해시로 만든 `source_key` 기준으로 중복 저장을 방지합니다.

## 페이지 수집 범위

기본값은 1페이지입니다. Actions YAML의 `IRIS_MAX_PAGES` 값을 늘릴 수 있습니다. 다만 IRIS의 페이지 파라미터는 사이트 변경 가능성이 있어 2페이지 이후는 환경에 따라 동작하지 않을 수 있습니다.
