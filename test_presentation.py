import copy
import unittest
from pathlib import Path
from html.parser import HTMLParser
from presentation import display_card, with_display, brief_explanation, brief_reply, valid_emphasis, choose_emphasis

class PresentationTests(unittest.TestCase):
    def test_person_specific_viewpoint_title(self):
        d=display_card({'text':'原文。','explanation':'有事实的批评才值得改。','viewpoint_title':'先查事实，再谈改变'})
        self.assertEqual(d['viewpoint_title'],'先查事实，再谈改变')

    def test_missing_title_uses_existing_key_phrase(self):
        d=display_card({'text':'原文。','explanation':'自责不等于有错。'})
        self.assertEqual(d['viewpoint_title'],'自责不等于有错')
    def test_main_reply_two_sentences(self):
        self.assertEqual(brief_reply('你不必把批评当成人格定论。中间解释一。中间解释二。你今天先写下具体事实。'),
                         '你不必把批评当成人格定论。你今天先写下具体事实。')
        self.assertEqual(brief_reply('你可以发消息：“明晚一起吃饭吗？”然后看看对方的回应。'),
                         '你可以发消息：“明晚一起吃饭吗？”然后看看对方的回应。')
        self.assertEqual(brief_reply('你先别急着自责。先写下具体行为。对方具体说了什么？你先记下来。', True),
                         '对方具体说了什么？')
    def test_insight_keeps_necessary_second_sentence(self):
        self.assertEqual(brief_explanation('解读：與朋友相處不必爭高低。謙讓不等於委屈自己。'),
                         '与朋友相处不必争高低。谦让不等于委屈自己。')
        card = display_card({'text': '朋友有信。', 'explanation': '先分清批評是否具體，不必全盤否定自己。'})
        self.assertEqual(card['explanation'], '先分清批评是否具体，不必全盘否定自己。')

    def test_emphasis_accepts_only_existing_short_spans(self):
        self.assertEqual(valid_emphasis('安稳不等于退步，尽责才是关键。',
            ['安稳不等于退步','不存在的词',None,'尽责才是关键','第三处']),['安稳不等于退步','尽责才是关键'])

    def test_missing_emphasis_still_marks_one_existing_judgment(self):
        text='想过平凡生活，安稳不等于退步。'
        emphasis=choose_emphasis(text,None)
        self.assertEqual(emphasis,['安稳不等于退步'])

    def test_emphasis_does_not_change_commentary_or_source(self):
        card={'text':'原文保持原样。','explanation':'安稳不等于退步。','emphasis':['安稳不等于退步']}
        before=copy.deepcopy(card); result=display_card(card)
        self.assertEqual(result['emphasis'],['安稳不等于退步'])
        self.assertEqual(card,before)
    def test_simplified_excerpt_preserves_source(self):
        text = '前文。' * 30 + '與朋友論學，須委曲善誘。' + '後文。' * 30
        a = text.index('與')
        card = dict(paragraph=text, quote='與朋友論學，須委曲善誘。', highlight_start=a,
                    highlight_end=a + len('與朋友論學，須委曲善誘。'), person='王陽明', work='傳習錄')
        original = copy.deepcopy(card)
        d = display_card(card)
        self.assertEqual(d['person'], '王阳明')
        self.assertEqual(d['excerpt'][d['highlight_start']:d['highlight_end']], '与朋友论学，须委曲善诱。')
        self.assertLess(len(d['excerpt']), 120)
        self.assertEqual(card, original)

    def test_only_response_copy_changes(self):
        response = {'result': {'synthesis': '請繼續', 'cards': []}, 'session_id': 'ABC'}
        self.assertEqual(with_display(response)['result']['display_reply'], '请继续')
        self.assertNotIn('display_reply', response['result'])
        self.assertEqual(with_display(response)['session_id'], 'ABC')

    def test_collapsed_quote_stays_short(self):
        text = '朋友相處，互相勸勉。' * 15
        card = dict(paragraph=text, quote=text[:150], highlight_start=0, highlight_end=150)
        displayed = display_card(card)
        self.assertLessEqual(len(displayed['excerpt']), 65)
        self.assertEqual(displayed['highlight_end'], 64)
        self.assertEqual(card['highlight_end'], 150)

    def test_reading_has_no_visible_section_titles(self):
        js = (Path(__file__).parent / 'web/app.js').read_text(encoding='utf-8')
        for label in ('本段原文', '白话翻译 · AI', '文字解读 · AI', '查看原始出处', '仅供阅读参考'):
            self.assertNotIn(label, js)

    def test_minimal_markup(self):
        class Tags(HTMLParser):
            def __init__(self): super().__init__(); self.tags = []
            def handle_starttag(self, tag, attrs): self.tags.append(tag)
        parser = Tags()
        parser.feed((Path(__file__).parent / 'web/index.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.tags.count('textarea'), 1)
        self.assertEqual(parser.tags.count('input'), 0)
        self.assertEqual(parser.tags.count('button'), 1)
        self.assertNotIn('header', parser.tags)
        self.assertNotIn('footer', parser.tags)

if __name__ == '__main__': unittest.main()
