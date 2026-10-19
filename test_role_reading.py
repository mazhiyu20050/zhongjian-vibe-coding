import unittest
from source_details import verify_reading_quotes, verify_role_focus
from query import address_reader
from person_skills import load_skills
from presentation import brief_explanation, brief_reply


class RoleReadingTests(unittest.TestCase):
    def test_introductory_filler_is_removed(self):
        text = '你可以这样理解：准备是在行动中完成的。'
        self.assertEqual(address_reader(text),'准备是在行动中完成的。')
        self.assertEqual(brief_explanation(text),'准备是在行动中完成的。')
        self.assertEqual(brief_reply('我的判断是：'+text),'准备是在行动中完成的。')
        self.assertEqual(brief_reply('我不赞成放弃学习。'),'我不赞成放弃学习。')
    def test_invented_quotation_rejected(self):
        for text in ('原文说“顺德不告而取”。','我说"顺德不告而取"。'):
            with self.assertRaises(ValueError):
                verify_reading_quotes(text,'舜之不告而娶。')

    def test_original_quote_can_display_simplified(self):
        verify_reading_quotes('我讲“权轻重之宜”，就是辨眼前轻重。','權輕重之宜。')

    def test_first_person_not_prefixed_with_third_party(self):
        self.assertEqual(address_reader('我不赞成一概而论。'),'我不赞成一概而论。')

    def test_each_skill_has_decisive_first_person_mode(self):
        for skill in load_skills().values():
            self.assertIn('第一人称',skill['instructions'])
            self.assertIn('明确判断',skill['instructions'])

    def test_third_party_and_unrelated_allusions_rejected(self):
        for text in ('这段原文说，舜也这样做。', '我讲舜之不告而娶。'):
            with self.assertRaises(ValueError):
                verify_role_focus(text,'权轻重之宜','恋爱一定浪费时间吗？')
        verify_role_focus('我不赞成一概断定，先守住学习责任。','权轻重之宜','恋爱一定浪费时间吗？')

    def test_unintroduced_person_needs_context(self):
        with self.assertRaises(ValueError):
            verify_role_focus('徐爱怕漏掉事理，我这样回答。','心外无理','安稳算退步吗？')
        verify_role_focus('我的学生徐爱曾问我，事理是否在心外。','心外无理','安稳算退步吗？')


if __name__ == '__main__':
    unittest.main()
