import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from agent import AgentService, limit_questions
from collections_store import CollectionStore
from test_query import source


def tool(name, args, cid='call1'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': cid, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


def final(cards=None, text='完成'):
    return {'role': 'assistant', 'content': json.dumps({'cards': cards or [], 'synthesis': text,
                                                       'evidence_scope': 'partial'}, ensure_ascii=False)}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CollectionStore(Path(self.tmp.name) / 'test.sqlite3')
        self.rows = [source('先生曰：朋友宜謙下。相交有信。')]

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_answers_force_actual_search_and_then_advice(self):
        client = Mock(side_effect=[final(text='你最难受的是哪个时段？'),
            final(text='你现在有可以联系的朋友吗？'),
            tool('search_sources', {'terms':['朋友']}, 'deadline-search'),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你先联系一位熟悉的朋友。'}], text='你今晚先约朋友聊十分钟。你还有别的困惑吗？')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('我最近独居很孤独')
        second = service.ask('晚上回家最孤独', first['session_id'])
        third = service.ask('有朋友，但最近很少联系', first['session_id'])['result']
        self.assertEqual(second['result']['clarification']['asked'], 2)
        self.assertEqual(third['clarification']['answered'], 2)
        self.assertEqual(third['clarification']['asked'], 2)
        self.assertFalse(third['clarification']['awaiting_answer'])
        self.assertTrue(third['advice_ready'])
        self.assertNotIn('？', third['synthesis'])
        self.assertEqual(len(third['cards']), 1)
        self.assertEqual(client.call_args_list[2].kwargs['tool_choice'], {'type':'function','function':{'name':'search_sources'}})
        self.assertIn('我最近独居很孤独', third['question_context'])

    def test_each_reply_asks_no_more_than_one_question(self):
        service = AgentService(self.rows, self.store, Mock(return_value=final(text='你最孤独是在什么时候？你有几个朋友？你愿意说吗？')))
        answer = service.ask('我想有人陪伴')['result']
        self.assertEqual(answer['synthesis'].count('？'), 1)
        self.assertEqual(answer['clarification']['asked'], 1)

    def test_quoted_invitation_is_not_mistaken_for_third_followup(self):
        text = '你可以发消息：“明晚一起吃饭吗？我请第一顿。”先约一次试试。你还有什么问题？'
        cleaned, asked = limit_questions(text, 0)
        self.assertEqual(cleaned, '你可以发消息：“明晚一起吃饭吗？我请第一顿。”先约一次试试。')
        self.assertEqual(asked, 0)

    def test_explicit_new_topic_resets_question_budget(self):
        client = Mock(side_effect=[final(text='你最孤独是什么时候？'), final(text='你最担心哪一点？')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('我想有人陪伴')
        answer = service.ask('换个话题，我担心工作', first['session_id'])['result']
        self.assertEqual(answer['clarification']['asked'], 1)
        self.assertEqual(answer['clarification']['answered'], 0)

    def test_can_retrieve_before_two_questions(self):
        client = Mock(side_effect=[final(text='你们具体争论什么？'),
            tool('search_sources', {'terms':['朋友']}),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你先听完朋友的理由。'}], text='你先听完，再说明自己的想法。')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('朋友之间总争高低')
        answer = service.ask('我们总比谁的成绩好', first['session_id'])['result']
        self.assertEqual(answer['clarification']['answered'], 1)
        self.assertTrue(answer['advice_ready'])
        self.assertEqual(len(answer['cards']), 1)

    def test_first_turn_can_search_and_answer_without_questions(self):
        client = Mock(side_effect=[tool('search_sources', {'terms':['朋友']}),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你今天先约一位熟悉的朋友吃饭。'}], text='你今天先发出一次具体邀请，见面后看看自己是否更放松。')])
        answer = AgentService(self.rows, self.store, client).ask('我独居，晚上孤独，想找人说说话')['result']
        self.assertEqual(answer['clarification']['asked'], 0)
        self.assertEqual(answer['clarification']['answered'], 0)
        self.assertFalse(answer['clarification']['awaiting_answer'])
        self.assertTrue(answer['advice_ready'])
        self.assertEqual(len(answer['cards']), 1)
        self.assertEqual(client.call_args_list[0].kwargs['tool_choice'], 'auto')

    def test_recommended_self_reflection_is_not_a_clarification_round(self):
        client=Mock(side_effect=[tool('search_sources', {'terms':['朋友']}),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你可以分清求理与求胜。'}],text='你可以问自己：这次我是在求理，还是在求胜？')])
        result=AgentService(self.rows,self.store,client).ask('朋友相处总想争高低')['result']
        self.assertEqual(result['clarification']['asked'],0)
        self.assertFalse(result['clarification']['awaiting_answer'])
        self.assertTrue(result['advice_ready'])

    def test_model_selects_real_search_and_cards(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([
            {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '仅供参考'}])])
        service = AgentService(self.rows, self.store, client)
        answer = service.ask('朋友怎么相处')
        self.assertEqual(answer['result']['cards'][0]['entry'], '214')
        self.assertEqual(answer['result']['tool_trace'][0]['status'], 'success')
        self.assertIn('tools', client.call_args_list[0].kwargs)
        sent = client.call_args_list[1].args[0]
        self.assertEqual(sent[-1]['role'], 'tool')

    def test_one_bounded_final_structure_repair(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}),
            {'role': 'assistant', 'content': json.dumps({'cards': {}, 'synthesis': {'wrong': 'type'}})},
            final([{'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '你先学会倾听。'}])])
        result = AgentService(self.rows, self.store, client).ask('朋友相处')
        self.assertEqual(len(result['result']['cards']), 1)
        self.assertEqual(client.call_count, 3)
        self.assertEqual(client.call_args.kwargs['tool_choice'], 'none')
        self.assertEqual(len(result['result']['tool_trace']), 1)

    def test_json_repair_still_has_room_after_five_tool_steps(self):
        client=Mock(side_effect=[tool('search_sources',{'terms':['朋友']},'search-'+str(i)) for i in range(5)]+[
            {'role':'assistant','content':'{"cards":['},
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你可以先听清朋友具体在说什么。'}])])
        answer=AgentService(self.rows,self.store,client).ask('朋友相处')['result']
        self.assertEqual(len(answer['cards']),1)
        self.assertEqual(client.call_count,7)
        self.assertEqual(client.call_args.kwargs['tool_choice'],'none')

    def test_incomplete_provider_response_has_one_bounded_regeneration(self):
        from check_api import ModelOutputTruncated
        client=Mock(side_effect=[ModelOutputTruncated('output_truncated'),
            tool('search_sources',{'terms':['朋友']}),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你可以先听清朋友具体在说什么。'}])])
        self.assertEqual(len(AgentService(self.rows,self.store,client).ask('朋友相处')['result']['cards']),1)
        self.assertEqual(client.call_count,3)

    def test_repeated_provider_json_error_stops_after_one_regeneration(self):
        client=Mock(side_effect=json.JSONDecodeError('invalid','x',0))
        from query import QueryStageError
        with self.assertRaises(QueryStageError) as error:
            AgentService(self.rows,self.store,client).ask('朋友相处')
        self.assertEqual(error.exception.code,'invalid_json')
        self.assertEqual(client.call_count,2)

    def test_one_bounded_invalid_json_repair(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}),
            {'role': 'assistant', 'content': '{"cards":['},
            final([{'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '你先学会倾听。'}])])
        answer = AgentService(self.rows, self.store, client).ask('朋友相处')
        self.assertEqual(len(answer['result']['cards']), 1)
        self.assertEqual(client.call_count, 3)
        self.assertEqual(client.call_args.kwargs['tool_choice'], 'none')

    def test_bad_source_is_repaired_with_allowed_literal_choices(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}),
            final([{'passage_id':'P999','quote_id':'Q1','explanation':'你先听听。'}]),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你先听听。'}])])
        answer = AgentService(self.rows, self.store, client).ask('朋友相处')
        self.assertEqual(len(answer['result']['cards']), 1)
        self.assertIn('允许来源', client.call_args.args[0][-1]['content'])
        self.assertEqual(client.call_count, 3)

    def test_multi_turn_state_and_context(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([
            {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '解读'}]),
            tool('get_context', {'source_id': 'P1'}, 'call2'), final(text='已查原文')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('查朋友')
        second = service.ask('看第一条上下文', first['session_id'])
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertTrue(second['result']['cards_retained'])
        self.assertEqual(second['result']['tool_trace'][0]['tool'], 'get_context')

    def test_new_loneliness_question_does_not_retain_criticism_cards(self):
        card = {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '你先反思争执中的具体行为。'}
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([card]),
            final(text='你独居时最难受的是哪一刻？')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('朋友批评我怎么办')
        answer = service.ask('我现在独居很孤独，大二了没有舍友。', first['session_id'])['result']
        self.assertEqual(answer['cards'], [])
        self.assertFalse(answer['cards_retained'])
        self.assertEqual(service.sessions[first['session_id']].last_cards, [])
        self.assertEqual(answer['terms'], [])

    def test_model_explicitly_reuses_old_card_on_new_topic_is_filtered(self):
        card = {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '你先反思具体行为。'}
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([card]),
            final([card], text='你在独居时需要更多陪伴。')])
        service = AgentService(self.rows, self.store, client)
        first = service.ask('朋友批评')
        answer = service.ask('我独居很孤独', first['session_id'])['result']
        self.assertEqual(answer['cards'], [])
        self.assertEqual(answer['stale_cards_removed'], 1)

    def test_new_search_does_not_admit_old_unreturned_evidence(self):
        rows = self.rows + [{**self.rows[0], 'id': 'unit-new', 'text': '独处时可以读书。'}]
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你先想清楚。'}]),
            tool('search_sources', {'terms': ['独处']}, 'new-search'),
            final([{'passage_id':'P1','quote_id':'Q1','explanation':'你需要陪伴。'}])])
        service = AgentService(rows, self.store, client)
        first = service.ask('朋友批评我')
        answer = service.ask('我现在独处', first['session_id'])['result']
        self.assertEqual(answer['cards'], [])
        self.assertEqual(answer['stale_cards_removed'], 1)

    def test_save_needs_confirmation_and_preserves_same_session(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([
            {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '解读'}]),
            tool('save_favorite', {'card_number': 1}, 'save1'), final(text='请确认'),
            tool('save_favorite', {'card_number': 1}, 'save2'), final(text='已收藏')])
        service = AgentService(self.rows, self.store, client)
        sid = service.ask('查朋友')['session_id']
        pending = service.ask('收藏第一条', sid)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(pending['result']['tool_trace'][0]['status'], 'needs_confirmation')
        service.ask('确认', sid)
        self.assertEqual(len(self.store.list()), 1)

    def test_bad_tool_recovers_without_program_restart(self):
        client = Mock(side_effect=[tool('get_context', {'source_id': 'P999'}),
                                   tool('search_sources', {'terms': ['朋友']}, 'call2'), final()])
        answer = AgentService(self.rows, self.store, client).ask('查观点')
        self.assertEqual([x['status'] for x in answer['result']['tool_trace']], ['error', 'success'])

    def test_missing_source_report_is_not_a_fabricated_citation(self):
        client = Mock(side_effect=[tool('get_context', {'source_id': 'P999'}),
            tool('search_sources', {'terms': ['朋友']}, 'retry'),
            final([{'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '资料说明'}],
                  text='P999不存在，改用P1提供参考。')])
        result = AgentService(self.rows, self.store, client).ask('编号错误后继续')
        self.assertNotIn('P999', result['result']['synthesis'])
        self.assertIn('未检索到', result['result']['synthesis'])

    def test_unknown_session_rejected(self):
        with self.assertRaises(ValueError):
            AgentService(self.rows, self.store, Mock()).ask('问题', 'foreign-session')

    def test_logs_contain_metadata_not_question(self):
        path = Path(self.tmp.name) / 'tools.jsonl'
        client = Mock(side_effect=[tool('list_favorites', {}), final()])
        AgentService(self.rows, self.store, client, path).ask('PRIVATE_QUESTION')
        text = path.read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE_', text)
        self.assertIn('list_favorites', text)

    def test_failed_final_keeps_completed_tool_state(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), TimeoutError(),
                                   tool('get_context', {'source_id': 'P1'}, 'nextcall'), final()])
        service = AgentService(self.rows, self.store, client)
        with self.assertRaises(TimeoutError) as caught:
            service.ask('查资料')
        sid = caught.exception.session_id
        result = service.ask('继续查上一条上下文', sid)
        self.assertEqual(result['session_id'], sid)
        self.assertEqual(result['result']['tool_trace'][0]['status'], 'success')
        self.assertTrue(any(m.get('role') == 'tool' for m in client.call_args_list[2].args[0]))

    def test_untrusted_tool_name_not_written_to_log(self):
        path = Path(self.tmp.name) / 'metadata.jsonl'
        client = Mock(side_effect=[tool('PRIVATE_NAME', {}, 'PRIVATE_CALL_ID'), final()])
        AgentService(self.rows, self.store, client, path).ask('PRIVATE_QUESTION')
        text = path.read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE_', text)
        self.assertIn('unknown_tool', text)

    def test_reset_ends_session(self):
        service = AgentService(self.rows, self.store, Mock(return_value=final()))
        sid = service.ask('你好')['session_id']
        service.reset(sid)
        service.reset(sid)  # idempotent reset after service expiry is harmless
        with self.assertRaises(ValueError):
            service.ask('继续', sid)

    def test_confirmation_without_pending_does_not_write(self):
        client = Mock(side_effect=[tool('search_sources', {'terms': ['朋友']}), final([
            {'passage_id': 'P1', 'quote_id': 'Q1', 'explanation': '解读'}]),
            tool('save_favorite', {'card_number': 1}, 'save'), final(text='待确认')])
        service = AgentService(self.rows, self.store, client)
        sid = service.ask('查资料')['session_id']
        result = service.ask('确认', sid)
        self.assertEqual(self.store.list(), [])
        self.assertTrue(result['result']['pending_confirmation'])

    def test_call_limit_is_enforced(self):
        client = Mock(side_effect=[tool('list_favorites', {}, 'c'+str(i)) for i in range(6)])
        with self.assertRaises(ValueError) as caught:
            AgentService(self.rows, self.store, client).ask('查看收藏')
        self.assertEqual(caught.exception.code, 'tool_budget')
        self.assertEqual(client.call_args.kwargs['tool_choice'], 'none')

    def test_claim_without_write_tool_is_not_reported_as_saved(self):
        result = AgentService(self.rows, self.store, Mock(return_value=final(text='已经收藏成功'))).ask('帮我收藏')
        self.assertIn('没有实际执行', result['result']['synthesis'])
        self.assertEqual(self.store.list(), [])


if __name__ == '__main__':
    unittest.main()
