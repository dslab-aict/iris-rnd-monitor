# IRIS R&D Announcement Monitor

IRIS 사업공고 페이지를 매일 수집해 `data/iris_announcements.csv`에 누적 저장합니다.

## 실행

```bash
python -m pip install -r requirements.txt
PYTHONPATH=src python -m iris_scraper --csv data/iris_announcements.csv --max-pages 1
```

## GitHub Actions

`.github/workflows/iris.yml`가 매일 00:00 KST에 실행됩니다.

- GitHub cron은 UTC 기준이므로 `0 15 * * *`가 한국시간 자정입니다.
- 수집 결과가 새 CSV 행을 만들면 자동 커밋합니다.
- 수집 0건이면 실패 처리하고 `debug_iris_page1.html` artifact를 업로드합니다.

## CSV 필드

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
- 수집일시_UTC
- source_key

## 중복 제거

`공고번호 + 공고명 + 공고일자`를 SHA-256으로 해시한 `source_key` 기준입니다.

## v3 수정 내용

이 버전은 IRIS의 현재 공개 HTML 구조에 맞춰 CSS selector가 아니라 텍스트 패턴으로 파싱합니다.

```text
소관부처 > 전문기관
공고명
공고번호 : ... 공고일자 : YYYY-MM-DD 공고상태 : ... 공모유형 : ...
```

따라서 `산업통상부>한국산업기술기획평가원`처럼 `>` 양옆 공백이 없는 경우도 처리합니다.
