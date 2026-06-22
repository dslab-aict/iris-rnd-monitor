from iris_scraper.scraper import parse_announcements_from_html


def test_parse_iris_text_pattern():
    html = """
    <html><body>
    전체 62 건 현재 페이지 1/7
    <ul><li>과학기술정보통신부 &gt; 한국연구재단</li></ul>
    <p>2026년 한-캐나다 이공계 대학원생 연수프로그램 공모</p>
    <p>공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중  공모유형 :자유공모</p>
    <p>접수중</p>
    <ul><li>산업통상부 &gt; 한국산업기술기획평가원</li></ul>
    <p>(수정) 2026년도 신규지원 대상과제 공고</p>
    <p>공고번호 :산업통상부 공고 제2026-433호 공고일자 :2026-06-15 공고상태 : 공고접수중  공모유형 :지정공모</p>
    <p>접수중</p>
    </body></html>
    """
    records = parse_announcements_from_html(html)
    assert len(records) == 2
    assert records[0].ministry == "과학기술정보통신부"
    assert records[0].agency == "한국연구재단"
    assert records[0].notice_no == "과학기술정보통신부 공고 제2026-0696호"
    assert records[0].notice_date == "2026-06-22"
    assert records[0].reception_started == "Y"
    assert records[1].competition_type == "지정공모"
