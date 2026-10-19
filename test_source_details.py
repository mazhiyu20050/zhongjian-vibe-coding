import json
import unittest
from unittest.mock import Mock
from source_details import build_details
from query import make_passages, QueryStageError
from test_query import source

class DetailTests(unittest.TestCase):
    def test_grounded_details(self):
        row = source('與朋友論學，須委曲善誘。')
        other = {**row, 'id': row['id'] + '-other', 'text': '朋友相處，當互相勸勉。'}
        passages = make_passages([row, other])
        client = Mock(return_value={'content': json.dumps({'reading': '與朋友討論學問。\n\n重視朋友交流。'})})
        result = build_details(passages[0], row, passages, client, question='我该先核实什么？')
        self.assertEqual(result['original'], '与朋友论学，须委曲善诱。')
        self.assertEqual(result['reading'], '与朋友讨论学问。\n\n重视朋友交流。')
        self.assertEqual(len(result['related']), 1)
        self.assertIn('朋友相处', result['related'][0]['text'])
        self.assertNotEqual(result['related'][0]['id'], passages[0]['id'])
        self.assertIn(row['text'], client.call_args.args[0][1]['content'])
        self.assertEqual(json.loads(client.call_args.args[0][1]['content'])['你的问题'], '我该先核实什么？')

    def test_bad_ai_output_rejected(self):
        row = source('朋友有信。')
        passages = make_passages([row])
        with self.assertRaises(QueryStageError):
            build_details(passages[0], row, passages, lambda _: {'content': '{"translation": ""}'})

if __name__ == '__main__': unittest.main()
