# IRIS R&D Announcement CSV Scraper

IRIS 사업공고 목록을 읽어 CSV에 누적 저장하는 GitHub Actions 프로젝트입니다.

## 포함 기능

- IRIS 사업공고 목록 수집
- CSV append
- `공고번호 + 공고명 + 공고일자` 기반 중복 방지
- 매일 00:00 KST 자동 실행
- 수동 실행 지원
- 0건 수집 시 실패 처리 및 debug HTML artifact 업로드

## CSV 컬럼

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

## 설치 및 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src python -m iris_scraper --csv data/iris_announcements.csv --max-pages 1
```

## GitHub Actions 실행

1. 이 프로젝트 파일 전체를 GitHub 저장소에 업로드합니다.
2. 저장소의 `Actions` 탭으로 이동합니다.
3. `IRIS RND Scraper` workflow를 선택합니다.
4. `Run workflow`를 누릅니다.

자동 실행은 `.github/workflows/iris.yml`의 다음 cron으로 설정되어 있습니다.

```yaml
- cron: "0 15 * * *"
```

GitHub Actions cron은 UTC 기준이므로 `15:00 UTC`가 한국시간 `00:00 KST`입니다.

## 이번 수정의 핵심

`BeautifulSoup(html, "lxml")`를 사용하지 않습니다. GitHub runner에 별도 native parser 설치가 없어도 동작하도록 Python 기본 HTML parser를 사용합니다.

```python
BeautifulSoup(html, "html.parser")
```

따라서 `requirements.txt`에는 `lxml`이 없습니다.

## 주의

IRIS 상세 페이지 링크가 서버 HTML에 직접 노출되지 않는 경우, `접수기간`, `사업담당자 연락처`, 상세 `바로 가기 링크`는 비어 있거나 목록 페이지 URL로 저장될 수 있습니다. 목록에서 확인 가능한 필드인 소관부처, 전문기관, 공고번호, 공고명, 공고일자, 접수상태, 공모유형은 파싱합니다.
