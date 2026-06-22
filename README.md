# IRIS R&D 사업공고 CSV 수집기

IRIS 사업공고 페이지를 매일 00:00 KST에 확인해 `data/iris_announcements.csv`에 신규 공고를 append합니다.

## 핵심 동작

- 대상: https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do
- 출력: `data/iris_announcements.csv`
- 중복 기준: `공고번호 + 공고명 + 공고일자`
- GitHub Actions: `.github/workflows/iris.yml`
- 실행 시간: 매일 00:00 KST (`cron: 0 15 * * *`, UTC 기준)

## CSV 컬럼

```text
소관부처,전문기관,공고번호,공고명,공고일자,접수기간,사업담당자 연락처,접수 개시 여부,바로 가기 링크,수집일시
```

## GitHub 설정

1. 이 폴더 내용을 GitHub 저장소 루트에 업로드합니다.
2. 저장소 `Settings > Actions > General`에서 Actions 실행을 허용합니다.
3. 저장소 `Settings > Actions > General > Workflow permissions`에서 `Read and write permissions`를 선택합니다.
4. `Actions > IRIS RND Announcement Scraper > Run workflow`로 수동 실행합니다.

## CSV가 업데이트되지 않을 때 확인할 것

Actions 로그에서 다음 줄을 확인합니다.

```text
[result] scraped=... appended=...
```

- `scraped > 0`, `appended = 0`: 이미 CSV에 같은 공고가 있어서 중복 방지로 건너뛴 것입니다.
- `scraped = 0`: IRIS 사이트 접근, HTML 구조 변경, 또는 네트워크 문제가 있습니다. 이 버전은 `IRIS_FAIL_ON_ZERO=true`라서 0건이면 workflow를 실패시킵니다.
- `git push` 권한 오류: 저장소 Settings에서 Workflow permissions를 `Read and write permissions`로 바꿔야 합니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src IRIS_OUTPUT_CSV=data/iris_announcements.csv python -m iris_scraper
```

## 상세 본문 필드 한계

IRIS 상세 페이지는 동적 UI와 사이트 구조에 따라 열람 방식이 바뀔 수 있습니다. 이 스크립트는 목록에서 안정적으로 얻을 수 있는 필드를 우선 저장하고, Playwright fallback에서 상세 본문 추출을 시도합니다. 상세 본문 추출이 실패해도 목록 필드는 CSV에 저장됩니다.
