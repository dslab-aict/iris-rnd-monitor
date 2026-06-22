from src.iris_scraper.scraper import parse_announcements_from_html


def test_parse_list_html():
    html = """
    <html><body>
    <p>전체 1 건 현재 페이지 1/1</p>
    <p>접수중</p>
    <p>과학기술정보통신부 &gt; 한국연구재단</p>
    <p>2026년 한-캐나다 이공계 대학원생 연수프로그램 공모</p>
    <p>공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중 공모유형 :자유공모</p>
    <p>접수중</p>
    </body></html>
    """
    rows = parse_announcements_from_html(html)
    assert len(rows) == 1
    assert rows[0].소관부처 == "과학기술정보통신부"
    assert rows[0].전문기관 == "한국연구재단"
    assert rows[0].공고번호 == "과학기술정보통신부 공고 제2026-0696호"
    assert rows[0].공고명 == "2026년 한-캐나다 이공계 대학원생 연수프로그램 공모"
    assert rows[0].공고일자 == "2026-06-22"
