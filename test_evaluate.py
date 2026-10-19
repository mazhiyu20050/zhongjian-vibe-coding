import unittest
from unittest.mock import Mock
from evaluate import evaluate_offline, evaluate_live
from query import QueryStageError


class EvaluationTests(unittest.TestCase):
    def test_insufficient_has_no_fabricated_pass(self):
        case = {'id': 'x', 'topic': '边界', 'question': '问题', 'offline_terms': ['朋友'],
                'reference_entries': [], 'evidence_scope': 'insufficient', 'review_rule': '资料不足'}
        result = evaluate_offline([], [case])[0]
        self.assertIsNone(result['reference_entry_hit'])
        self.assertIsNone(result['relevance_review'])

    def test_sample_failure_is_retained(self):
        from unittest.mock import patch
        cases = [{'id': x, 'topic': '测试', 'question': '测试', 'review_rule': '', 'evidence_scope': 'partial'}
                 for x in ['a', 'b']]
        with patch('evaluate.query', side_effect=[QueryStageError('观点生成', 'output_truncated', '截断'), {'cards': []}]):
            results = evaluate_live([], cases, Mock())
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['status'], 'failed')
        self.assertEqual(results[1]['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
