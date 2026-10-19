import unittest
import io
import json
from unittest.mock import patch
import check_api
from check_api import execute_tool, complete


class ToolTests(unittest.TestCase):
    def test_valid(self):
        result = execute_tool('get_project_scope', '{}')
        self.assertEqual(result['project'], '众见')
        self.assertIn('人物专属智能体', result['excluded'])

    def test_unknown(self):
        with self.assertRaises(ValueError):
            execute_tool('unknown', '{}')

    def test_extra_arguments(self):
        with self.assertRaises(ValueError):
            execute_tool('get_project_scope', '{"extra": 1}')

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            execute_tool('get_project_scope', 'broken')

    def test_transport_valid_utf8_and_json_mode(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"terms":["朋友"]}'}}]}
        with patch('check_api.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result = complete('sk-test-fixture', 'deepseek-flash', [{'role': 'user', 'content': '朋友'}],
                              response_format={'type': 'json_object'})
        self.assertIn('朋友', result['content'])
        request = call.call_args.args[0]
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['messages'][0]['content'], '朋友')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})

    def test_response_shape_diagnostics(self):
        error_type = getattr(check_api, 'APIResponseError', None)
        self.assertIsNotNone(error_type)
        fixtures = [([], 'response_not_object'), ({}, 'choices_missing'),
                    ({'error': {'message': 'PRIVATE_RESPONSE'}}, 'provider_error'),
                    ({'choices': []}, 'choices_empty'),
                    ({'choices': [{}]}, 'message_missing'),
                    ({'choices': [{'message': 'PRIVATE_RESPONSE'}]}, 'message_not_object')]
        for response, code in fixtures:
            with self.subTest(code=code), patch('check_api.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(error_type) as caught:
                    complete('sk-test-fixture', 'deepseek-flash', [])
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('PRIVATE_RESPONSE', str(caught.exception))

    def test_non_ascii_key_never_sent(self):
        error_type = getattr(check_api, 'APIResponseError', None)
        self.assertIsNotNone(error_type)
        with patch('check_api.urllib.request.urlopen') as call:
            with self.assertRaises(error_type) as caught:
                complete('PRIVATE_中文密钥', 'deepseek-flash', [])
            call.assert_not_called()
            self.assertEqual(caught.exception.code, 'key_invalid_characters')
            self.assertNotIn('PRIVATE_', str(caught.exception))

    def test_truncated_response_never_treated_as_valid_json(self):
        result = {'choices': [{'finish_reason': 'length', 'message': {'content': '{"cards":'}}]}
        with self.assertRaises(check_api.ModelOutputTruncated):
            check_api.parse_response(result)


if __name__ == '__main__':
    unittest.main()
