from iris_scraper import parse_list_html

SAMPLE = '''
<html><body>
전체 62 건 현재 페이지 1/7
<ul><li>과학기술정보통신부 &gt; 한국연구재단</li></ul>
2026년 한-캐나다 이공계 대학원생 연수프로그램 공모
공고번호 :과학기술정보통신부 공고 제2026-0696호 공고일자 :2026-06-22 공고상태 : 공고접수중 공모유형 :자유공모
접수중
<ul><li>산업통상부 &gt; 한국산업기술기획평가원</li></ul>
(수정) 테스트 공고
공고번호 :산업통상부 공고 제2026-433호 공고일자 :2026-06-15 공고상태 : 공고접수중 공모유형 :지정공모
접수중
</body></html>
'''

def test_parse_list_html():
    rows = parse_list_html(SAMPLE)
    assert len(rows) == 2
    assert rows[0].소관부처 == '과학기술정보통신부'
    assert rows[0].전문기관 == '한국연구재단'
    assert rows[0].공고번호 == '과학기술정보통신부 공고 제2026-0696호'
    assert rows[0].공고일자 == '2026-06-22'
    assert rows[0].접수_개시_여부 == 'Y'
