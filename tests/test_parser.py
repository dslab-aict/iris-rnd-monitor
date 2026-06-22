from iris_scraper.scraper import extract_total_pages, parse_detail_fields, parse_list_records

SAMPLE_LIST = """
전체 62 건 현재 페이지 1/7
접수중
과학기술정보통신부 > 한국연구재단
2026년 한-캐나다 이공계 대학원생 연수프로그램 공모
공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중 공모유형 :자유공모
접수중
산업통상부 > 한국산업기술기획평가원
(수정) 2026년도 제3차 조선해양산업기술개발사업 신규지원 대상과제 공고
공고번호 :산업통상부 공고 제2026-433호 공고일자 :2026-06-15 공고상태 : 공고접수중 공모유형 :지정공모
"""

SAMPLE_DETAIL = """
사업공고 상세
접수기간 : 2026.06.22 ~ 2026.07.22 18:00까지
사업담당자 문의: 홍길동 042-123-4567 test@example.kr
"""


def test_parse_list_records():
    rows = parse_list_records(SAMPLE_LIST)
    assert len(rows) == 2
    assert rows[0].ministry == "과학기술정보통신부"
    assert rows[0].agency == "한국연구재단"
    assert rows[0].notice_no == "과학기술정보통신부 공고 제2026-0696호"
    assert rows[0].notice_date == "2026-06-22"


def test_extract_total_pages():
    assert extract_total_pages(SAMPLE_LIST) == 7


def test_parse_detail_fields():
    fields = parse_detail_fields(SAMPLE_DETAIL)
    assert "2026.06.22" in fields["period"]
    assert "042-123-4567" in fields["contact"]
    assert "test@example.kr" in fields["contact"]

from iris_scraper.scraper import extract_detail_link_from_html, normalize_iris_detail_link


def test_normalize_share_link():
    link = normalize_iris_detail_link('/contents/retrieveBsnsAncmView.do?ancmId=022515&ancmPrg=ancmIng')
    assert link == 'https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=022515&ancmPrg=ancmIng'


def test_extract_detail_link_from_html_script_values():
    html = """
    <input type="hidden" name="ancmId" value="022515">
    <input type="hidden" name="ancmPrg" value="ancmIng">
    <button>링크공유</button>
    """
    assert extract_detail_link_from_html(html) == 'https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=022515&ancmPrg=ancmIng'


def test_extract_detail_link_from_share_popup_text():
    html = """
    <div>https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=022515&ancmPrg=ancmIng</div>
    """
    assert extract_detail_link_from_html(html).endswith('ancmId=022515&ancmPrg=ancmIng')
