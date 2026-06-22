# IRIS 국가연구개발 사업공고 CSV 수집기

IRIS 사업공고 페이지를 매일 확인하고, 신규 공고를 `data/iris_announcements.csv`에 누적 저장합니다.

대상 URL: https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do

## 수집 필드

| 필드 | 설명 |
|---|---|
| 소관부처 | 목록의 `소관부처 > 전문기관` 중 앞부분 |
| 전문기관 | 목록의 `소관부처 > 전문기관` 중 뒷부분 |
| 공고번호 | IRIS 공고번호 |
| 공고명 | 공고 제목 |
| 공고일자 | 공고 게시일 |
| 접수기간 | 상세 본문에서 추출 시도 |
| 사업담당자 연락처 | 상세 본문에서 전화번호/문의처 추출 시도 |
| 접수 개시 여부 | 접수중, 접수예정, 마감 등 |
| 바로 가기 링크 | 상세 페이지 URL. 상세 접근 실패 시 목록 URL |
| 수집일시 | KST 기준 수집 시간 |

중복 방지 기준은 `공고번호 + 공고명 + 공고일자`입니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
PYTHONPATH=src python -m iris_scraper
```

결과 CSV:

```text
data/iris_announcements.csv
```

환경변수:

```bash
IRIS_OUTPUT_CSV=data/iris_announcements.csv
IRIS_MAX_PAGES=10
IRIS_HEADLESS=true
```

## GitHub Actions 설정

1. GitHub에서 새 저장소를 만듭니다.
2. 이 프로젝트의 모든 파일을 저장소 루트에 업로드합니다.
3. 저장소의 `Actions` 탭에서 workflow를 활성화합니다. GitHub의 Node.js 20 deprecation 경고를 피하기 위해 `actions/checkout@v5`, `actions/setup-python@v6`, `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`를 사용합니다.
4. `Actions > IRIS RND Announcement Scraper > Run workflow`로 최초 1회 수동 실행합니다.

자동 실행 시간은 `.github/workflows/iris.yml`에 정의되어 있습니다.

```yaml
schedule:
  - cron: '0 15 * * *'
```

GitHub Actions는 UTC 기준이므로 `0 15 * * *`는 한국시간 매일 00:00입니다.

## 작동 방식

1. Playwright로 IRIS 목록 페이지를 엽니다.
2. 현재 페이지의 공고 카드를 텍스트 기반으로 파싱합니다.
3. 공고 제목을 클릭해 상세 본문 접근을 시도합니다.
4. 상세 본문에서 접수기간과 사업담당자 연락처를 정규식으로 추출합니다.
5. 다음 페이지로 이동하며 `IRIS_MAX_PAGES`까지 반복합니다.
6. 기존 CSV를 읽어 중복 키를 제외하고 새 행만 append합니다.
7. GitHub Actions가 CSV 변경분을 자동 commit/push합니다.

## 주의사항

IRIS 화면 구조나 상세 페이지 클릭 방식이 변경되면 상세 본문 추출이 실패할 수 있습니다. 이 경우에도 목록에서 확인 가능한 필드(소관부처, 전문기관, 공고번호, 공고명, 공고일자, 접수상태)는 가능한 범위에서 저장됩니다.

사이트가 자동화 접근을 차단하거나 로그인/세션이 필요한 상세 페이지로 변경되면, Playwright 클릭 로직을 수정해야 합니다.
