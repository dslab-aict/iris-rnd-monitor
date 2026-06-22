from iris_scraper.scraper import parse_announcements_from_html

SAMPLE = '''
<html><body>
전체 62 건 현재 페이지 1/7
접수중
과학기술정보통신부 > 한국연구재단
2026년 한-캐나다 이공계 대학원생 연수프로그램 공모
공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중 공모유형 :자유공모
접수중
산업통상부>한국산업기술기획평가원
(수정) 2026년도 제3차 조선해양산업기술개발사업 신규지원 대상과제 공고
공고번호 :산업통상부 공고 제2026-433호 공고일자 :2026-06-15 공고상태 : 공고접수중 공모유형 :지정공모
</body></html>
'''

def test_parse_current_iris_text_shape():
    rows = parse_announcements_from_html(SAMPLE)
    assert len(rows) == 2
    assert rows[0].ministry == '과학기술정보통신부'
    assert rows[0].agency == '한국연구재단'
    assert rows[0].notice_no == '과학기술정보통신부 공고 제2026-0696호'
    assert rows[0].notice_date == '2026-06-22'
    assert rows[0].reception_started == 'Y'
    assert rows[1].agency == '한국산업기술기획평가원'
