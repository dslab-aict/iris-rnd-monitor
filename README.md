# IRIS R&D 사업공고 모니터

IRIS 사업공고 페이지를 매일 00:00 KST에 수집해 `data/iris_announcements.csv`에 append합니다.

## 동작 방식

이 버전은 단순 목록 CSV가 아닙니다.

1. IRIS 목록 첫 화면에서 `현재 페이지 n/m`을 읽어 전체 페이지 수를 자동 감지합니다.
2. 1페이지부터 끝 페이지까지 순회합니다.
3. 각 페이지의 공고 목록을 파싱합니다.
4. 각 공고 제목을 Playwright로 클릭해 상세 화면을 엽니다.
5. 상세 본문에서 `접수기간`, 연락처/이메일, 본문 요약을 추출합니다.
6. `공고번호 + 공고명 + 공고일자` 해시로 중복 append를 방지합니다.

## GitHub Actions

`.github/workflows/iris.yml`가 포함되어 있습니다.

- 자동 실행: 매일 00:00 KST
- 수동 실행: Actions > IRIS RND Scraper > Run workflow
- `max_pages=0`: 전체 페이지 자동 수집
- 디버그 HTML: 실패 여부와 관계없이 artifact로 업로드

## 로컬 실행

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
PYTHONPATH=src python -m iris_scraper --csv data/iris_announcements.csv --max-pages 0 --details --debug-dir debug
```

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
- 상세본문요약
- 수집일시_UTC
- source_key

## 문제 발생 시 확인

Actions 실행 후 artifact `iris-debug-html`을 내려받아 다음 파일을 확인하세요.

- `debug_iris_list_page*.html`: 각 목록 페이지
- `debug_iris_detail_p*_i*.html`: 각 상세 클릭 결과

상세 클릭 후 여전히 목록 HTML만 저장되면 IRIS가 클릭 이벤트를 변경한 것이므로, 해당 debug HTML을 공유해야 정확한 클릭 selector를 보정할 수 있습니다.
