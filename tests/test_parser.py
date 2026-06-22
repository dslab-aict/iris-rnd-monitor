from iris_scraper.scraper import parse_announcements_from_html


def test_parse_iris_list_text():
    html = '''
    <html><body>
    <p>전체 62 건 현재 페이지 1/7</p>
    <p>#### 접수중</p>
    <ul><li>과학기술정보통신부 &gt; 한국연구재단</li></ul>
    <p>2026년 한-캐나다 이공계 대학원생 연수프로그램 공모</p>
    <p>공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중 공모유형 :자유공모</p>
    <p>접수중</p>
    </body></html>
    '''
    records = parse_announcements_from_html(html)
    assert len(records) == 1
    assert records[0].소관부처 == '과학기술정보통신부'
    assert records[0].전문기관 == '한국연구재단'
    assert records[0].공고번호 == '과학기술정보통신부 공고 제2026-0696호'
    assert records[0].공고일자 == '2026-06-22'
    assert records[0].접수_개시_여부 == '접수중'
