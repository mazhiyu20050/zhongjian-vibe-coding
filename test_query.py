import unittest
import json
from unittest.mock import Mock
import query as query_module
from query import make_passages, query, validate_terms, validate_answer


def source(text, kind='source'):
    return {'id': 'unit1', 'text': text, 'kind': kind, 'work': '传习录', 'volume': '卷下',
            'section': '门人记录', 'entry': '214', 'person': '王阳明',
            'source_url': 'https://zh.wikisource.org/wiki/test', 'text_reviewed': False,
            'speaker_note': '问答原文，逐句说话人待复核', 'quality_warning': '待校对'}


class QueryTests(unittest.TestCase):
    def test_passages_preserve_offsets(self):
        row = source('第一段。\n\n先生曰：朋友当互相帮助。')
        chunks = make_passages([row])
        self.assertEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(row['text'][chunk['start']:chunk['end']], chunk['text'])

    def test_exclude_editorial(self):
        self.assertEqual(make_passages([source('序言', 'editorial')]), [])

    def test_terms_validation(self):
        for terms in ([], ['a'], ['朋'], ['朋友'] * 2, ['x' * 21], '朋友', [1]):
            with self.subTest(terms=terms), self.assertRaises(ValueError):
                validate_terms(terms)
        self.assertEqual(validate_terms(['朋友', '謙下']), ['朋友', '謙下'])

    def test_quote_must_exist(self):
        passage = make_passages([source('先生曰：朋友宜謙下。')])[0]
        with self.assertRaises(ValueError):
            validate_answer({'cards': [{'passage_id': passage['id'], 'quote': '编造名言',
                                       'explanation': '说明'}], 'synthesis': '分析'}, [passage])

    def test_quote_id_resolves_to_verbatim_source(self):
        passage = make_passages([source('先生曰：朋友宜謙下。')])[0]
        answer = {'cards': [{'passage_id': passage['id'], 'quote_id': 'Q1',
                             'explanation': '系统解读'}], 'synthesis': '分析'}
        result = validate_answer(answer, [passage])
        self.assertEqual(result['cards'][0]['quote'], passage['text'])

    def test_unknown_quote_id_is_rejected(self):
        passage = make_passages([source('先生曰：朋友宜謙下。')])[0]
        with self.assertRaises(ValueError):
            validate_answer({'cards': [{'passage_id': passage['id'], 'quote_id': 'Q999',
                                       'explanation': '说明'}], 'synthesis': '分析'}, [passage])

    def test_candidate_spans_match_source(self):
        from query import quote_candidates
        text = '先生曰：「' + '甲' * 260 + '。」\n又問：何如？'
        for item in quote_candidates(text):
            self.assertEqual(text[item['start']:item['end']], item['text'])
            self.assertLessEqual(len(item['text']), 120)

    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            validate_answer({'cards': [{'passage_id': 'unknown', 'quote': '朋友',
                                       'explanation': '说明'}], 'synthesis': '分析'}, [])

    def test_reject_duplicate_cards(self):
        passage = make_passages([source('先生曰：朋友宜謙下。')])[0]
        card = {'passage_id': passage['id'], 'quote': '朋友', 'explanation': '说明'}
        with self.assertRaises(ValueError):
            validate_answer({'cards': [card, card], 'synthesis': '分析'}, [passage])

    def test_highlight_offsets(self):
        passage = make_passages([source('先生曰：朋友宜謙下。')])[0]
        result = validate_answer({'cards': [{'passage_id': passage['id'], 'quote': '朋友宜謙下',
                                            'explanation': '系统解读'}], 'synthesis': '应用分析'}, [passage])
        card = result['cards'][0]
        self.assertEqual(card['paragraph'][card['highlight_start']:card['highlight_end']], card['quote'])

    def test_pipeline_mock_not_live(self):
        rows = [source('先生曰：朋友宜謙下。')]
        passage = make_passages(rows)[0]
        client = Mock(side_effect=[{'content': '{"terms":["朋友","謙下"]}'},
                                   {'content': '{"cards":[{"passage_id":"' + passage['id'] +
                                    '","quote":"朋友宜謙下","explanation":"系统解读"}],"synthesis":"不同情境需区分。"}'}])
        result = query('朋友骂我怎么办', rows, lambda messages: client(messages))
        self.assertEqual(result['cards'][0]['entry'], '214')
        self.assertEqual(client.call_count, 2)
        self.assertEqual(result['verification'], '原文子串与来源 ID 校验通过；历史归属、解读质量待人工核对')

    def test_model_uses_short_source_alias(self):
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': '{"cards":[{"passage_id":"P1","quote_id":"Q1","explanation":"分析"}],"synthesis":"分析"}'}])
        result = query('问题', [source('先生曰：朋友宜謙下。')], client)
        self.assertEqual(result['cards'][0]['unit_id'], 'unit1')
        request = json.loads(client.call_args.args[0][1]['content'])
        self.assertEqual(request['evidence'][0]['id'], 'P1')

    def test_same_source_cards_merge_after_validation(self):
        card = {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '说明'}
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': json.dumps({'cards': [card, card], 'synthesis': '两条观点'})}])
        result = query('问题', [source('先生曰：朋友宜謙下。')], client)
        self.assertEqual(len(result['cards']), 1)
        self.assertEqual(result['duplicate_cards_removed'], 1)
        self.assertEqual(result['synthesis'], '两条观点')

    def test_merge_preserves_both_quotes_and_explanations(self):
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': json.dumps({'cards': [
                {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '解释甲'},
                {'passage_id': 'P1', 'quote_id': 'Q2', 'explanation': '解释乙'}],
                'synthesis': 'P1提供两点参考。', 'evidence_scope': 'partial'})}])
        result = query('问题', [source('朋友有信。相交宜謙下。')], client)
        card = result['cards'][0]
        self.assertIn('解释甲', card['explanation'])
        self.assertIn('解释乙', card['explanation'])
        self.assertEqual(len(card['supporting_quotes']), 2)
        self.assertNotIn('P1', result['synthesis'])
        self.assertIn('第214条', result['synthesis'])

    def test_insufficient_evidence_notice(self):
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': json.dumps({'cards': [], 'synthesis': '仅供参考', 'evidence_scope': 'insufficient'})}])
        result = query('我需要爱情还是友情', [source('朋友有信。')], client)
        self.assertEqual(result['evidence_scope'], 'insufficient')
        self.assertIn('资料不足', result['scope_notice'])

    def test_bad_scope_rejected(self):
        p = make_passages([source('朋友有信。')])[0]
        with self.assertRaises(ValueError):
            validate_answer({'cards': [], 'synthesis': '分析', 'evidence_scope': 'invented'}, [p])

    def test_merge_does_not_hide_invalid_second_quote(self):
        cards = [{'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '说明'},
                 {'passage_id': 'P1', 'quote_id': 'Q999', 'explanation': '说明'}]
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': json.dumps({'cards': cards, 'synthesis': '分析'})}])
        with self.assertRaises(query_module.QueryStageError) as caught:
            query('问题', [source('朋友有信。')], client)
        self.assertEqual(caught.exception.code, 'invalid_quote_id')

    def test_unknown_analysis_reference_rejected(self):
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': '{"cards":[],"synthesis":"见P999。","evidence_scope":"insufficient"}'}])
        with self.assertRaises(query_module.QueryStageError) as caught:
            query('问题', [source('朋友有信。')], client)
        self.assertEqual(caught.exception.code, 'unknown_analysis_source')

    def test_empty_results_no_second_model_call(self):
        client = Mock(return_value={'content': '{"terms":["星际航行"]}'})
        result = query('太空问题', [source('朋友宜謙下。')], client)
        self.assertEqual(result['cards'], [])
        self.assertEqual(client.call_count, 1)

    def test_model_json_error(self):
        with self.assertRaises(ValueError):
            query('问题', [], Mock(return_value={'content': 'not json'}))

    def test_keyword_error_has_safe_stage(self):
        error_type = getattr(query_module, 'QueryStageError', None)
        self.assertIsNotNone(error_type, '应有分阶段错误类型，避免所有错误都显示同一句话')
        with self.assertRaises(error_type) as caught:
            query('PRIVATE_QUESTION', [], Mock(return_value={'content': 'PRIVATE_MODEL_TEXT'}))
        self.assertEqual(caught.exception.stage, '关键词转换')
        self.assertEqual(caught.exception.code, 'invalid_json')
        self.assertNotIn('PRIVATE_', str(caught.exception))

    def test_quote_error_has_safe_stage(self):
        row = source('先生曰：朋友宜謙下。')
        pid = make_passages([row])[0]['id']
        client = Mock(side_effect=[{'content': '{"terms":["朋友"]}'},
            {'content': json.dumps({'cards': [{'passage_id': pid, 'quote': '编造引语',
                                               'explanation': '说明'}], 'synthesis': '分析'})}])
        error_type = getattr(query_module, 'QueryStageError', None)
        self.assertIsNotNone(error_type)
        with self.assertRaises(error_type) as caught:
            query('问题', [row], client)
        self.assertEqual(caught.exception.stage, '原文引用核验')
        self.assertEqual(caught.exception.code, 'quote_not_exact')

    def test_truncation_is_distinguished(self):
        error_type = getattr(query_module, 'QueryStageError', None)
        self.assertIsNotNone(error_type)
        with self.assertRaises(error_type) as caught:
            query('问题', [], Mock(return_value={'content': '{"terms":', '_finish_reason': 'length'}))
        self.assertEqual(caught.exception.code, 'output_truncated')

    def test_query_client_disables_thinking_and_has_output_headroom(self):
        factory = getattr(query_module, 'make_model_client', None)
        self.assertIsNotNone(factory)
        from unittest.mock import patch
        with patch('query.complete', return_value={'content': '{"terms":["朋友"]}'}) as complete:
            client = factory('sk-test-fixture', 'deepseek-flash')
            client([{'role': 'user', 'content': 'json test'}])
        self.assertEqual(complete.call_args.kwargs['thinking'], {'type': 'disabled'})
        self.assertEqual(complete.call_args.kwargs['response_format'], {'type': 'json_object'})
        self.assertGreaterEqual(complete.call_args.kwargs['max_tokens'], 4096)


if __name__ == '__main__':
    unittest.main()
