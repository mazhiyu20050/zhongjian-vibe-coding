import json
import unittest

from conversation_outline import outline, outline_events


class ConversationOutlineTests(unittest.TestCase):
    def setUp(self):
        self.turns = [
            {'question': '队友拖延怎么办？', 'result': {'cards': [
                {'person': '王阳明', 'explanation': '到实际任务里看看哪里卡住。'},
                {'person': '孔子', 'explanation': '先问队友是否遇到困难。'},
                {'person': '老子', 'explanation': '把交付缩成一步，看看哪里做不动。'},
            ]}},
            {'question': '如果他今晚还没交呢？', 'result': {'cards': [
                {'person': '王阳明', 'explanation': '到点只补关键任务。'},
            ]}},
        ]
        self.events = outline_events(self.turns)

    def result(self, nodes, consensus):
        return outline(self.events, lambda messages: {
            'content': json.dumps({'nodes': nodes, 'consensus': consensus}, ensure_ascii=False)})

    def test_shared_replies_keep_every_name_in_one_timeline_point(self):
        result = self.result([
            {'ids': [0], 'text': '队友拖延怎么办？'},
            {'ids': [1, 2, 3], 'text': '先找卡点。然后再分工。'},
            {'ids': [4], 'text': '今晚没交怎么办？'},
        ], {'ids': [1, 2, 3], 'text': '先查卡点，再行动。下一步看情况。'})
        self.assertEqual([n['kind'] for n in result['nodes']], ['question', 'reply', 'followup'])
        self.assertEqual(result['nodes'][1]['speakers'], ['王阳明', '孔子', '老子'])
        self.assertEqual(result['nodes'][1]['text'], '先找卡点。')
        self.assertEqual(result['consensus'], {'text': '先查卡点，再行动。', 'speakers': ['王阳明', '孔子', '老子']})

    def test_invalid_consensus_is_not_shown_as_agreement(self):
        nodes = [{'ids': [0], 'text': '队友拖延？'}, {'ids': [1], 'text': '先找卡点。'},
                 {'ids': [4], 'text': '今晚没交？'}]
        for invalid in (None, {'ids': [1, 5], 'text': '两个人都赞成。'},
                        {'ids': [0, 1], 'text': '两个人都赞成。'}, {'ids': [2, 999], 'text': '杜撰。'}):
            self.assertIsNone(self.result(nodes, invalid)['consensus'])

    def test_group_cannot_cross_a_followup_or_skip_it(self):
        with self.assertRaises(ValueError):
            self.result([{'ids': [0], 'text': '第一问。'}, {'ids': [1, 5], 'text': '跨轮回复。'},
                         {'ids': [4], 'text': '第二问。'}], None)

    def test_offline_excerpt_is_labeled_without_ai_consensus(self):
        result = outline(self.events)
        self.assertEqual(result['mode'], 'excerpt')
        self.assertIsNone(result['consensus'])


if __name__ == '__main__':
    unittest.main()
