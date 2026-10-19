"""DeepSeek smoke test. Credentials are entered privately and never saved."""
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = 'https://api.deepseek.com'
TOOL = {'type': 'function', 'function': {
    'name': 'get_project_scope',
    'description': '读取众见当前已确认的项目范围。',
    'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
}}


class ModelOutputTruncated(ValueError):
    """Transport succeeded, but the model output reached the token budget."""


class APIResponseError(ValueError):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(f'{code}: {reason}')


def parse_response(result):
    if not isinstance(result, dict):
        raise APIResponseError('response_not_object', '接口响应顶层不是 JSON 对象')
    if 'error' in result:
        raise APIResponseError('provider_error', '接口返回 error 字段，而不是正常对话结果')
    if 'choices' not in result:
        raise APIResponseError('choices_missing', '接口响应缺少 choices 字段')
    choices = result['choices']
    if not isinstance(choices, list):
        raise APIResponseError('choices_not_array', '接口响应 choices 不是列表')
    if not choices:
        raise APIResponseError('choices_empty', '接口响应 choices 列表为空')
    choice = choices[0]
    if not isinstance(choice, dict):
        raise APIResponseError('choice_not_object', '接口响应 choices[0] 不是对象')
    if choice.get('finish_reason') == 'length':
        raise ModelOutputTruncated('output_truncated')
    if 'message' not in choice:
        raise APIResponseError('message_missing', '接口响应 choices[0] 缺少 message')
    if not isinstance(choice['message'], dict):
        raise APIResponseError('message_not_object', '接口响应 message 不是对象')
    return choice['message']


def execute_tool(name, arguments):
    if name != 'get_project_scope':
        raise ValueError('工具名称不在允许列表中')
    if json.loads(arguments) != {}:
        raise ValueError('此工具只接受空对象参数')
    return {'project': '众见', 'scope': '本地观点查询、原文上下文、收藏管理',
            'excluded': '人物专属智能体、联网检索', 'source': '用户已确认的产品范围'}


def complete(key, model, messages, **options):
    if not isinstance(key, str) or not key or not all(33 <= ord(c) <= 126 for c in key):
        raise APIResponseError('key_invalid_characters', '密钥含空白、中文或其他非标准字符，请重新粘贴新密钥')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', model):
        raise APIResponseError('model_invalid_characters', '模型名称含异常字符，请按回车使用默认名称')
    payload = {'model': model, 'messages': messages, 'max_tokens': 800,
               'stream': False, **options}
    request = urllib.request.Request(
        BASE_URL + '/chat/completions',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        method='POST')
    # No automatic retry: keep smoke-test cost and writes predictable.
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
    return parse_response(result)


def main():
    key = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('请输入新密钥（隐藏输入，仅本次进程使用）：')
    key = key.strip()
    if not key:
        print('未输入密钥，测试未执行。')
        return 2
    model = os.environ.get('DEEPSEEK_MODEL') or input('模型名称 [deepseek-flash]：').strip() or 'deepseek-flash'
    print('本测试最多发送 3 次请求，产生少量 API 费用；不发送个人困惑或真实资料。')
    if input('输入 Y 开始：').strip().lower() != 'y':
        print('已取消。')
        return 0
    message = complete(key, model, [{'role': 'user', 'content': '请只回复：连接成功'}])
    if not message.get('content'):
        raise ValueError('普通对话未返回正文')
    print('[1/3] 普通对话通过')
    messages = [{'role': 'system', 'content': '你是众见的接口测试助手。项目范围须调用工具读取。'},
                {'role': 'user', 'content': '读取当前项目范围，告诉我首版是否包含人物智能体。'}]
    message = complete(key, model, messages, tools=[TOOL], tool_choice='auto')
    calls = message.get('tool_calls') or []
    if not calls:
        raise ValueError('本次模型没有选择工具；保留为未通过，不冒充成功')
    messages.append(message)  # Preserve tool-call IDs and any provider fields.
    for call in calls:
        result = execute_tool(call['function']['name'], call['function']['arguments'])
        messages.append({'role': 'tool', 'tool_call_id': call['id'],
                         'content': json.dumps(result, ensure_ascii=False)})
    print('[2/3] 模型选择工具、参数校验、本地执行通过')
    final = complete(key, model, messages, tools=[TOOL], tool_choice='none')
    if not final.get('content') or final.get('tool_calls'):
        raise ValueError('工具结果回传后未得到最终正文')
    print('[3/3] 工具结果回传与最终回复通过')
    print('模型实际回复：\n' + final['content'])
    print('请核对回复是否与工具范围一致。本测试仅验证接口闭环，不代表项目验收通过。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except urllib.error.HTTPError as exc:
        # Never print server body/request headers: they might echo credentials.
        hints = {401: '密钥认证失败，请检查新密钥', 402: '请检查账户余额',
                 429: '触发请求限制，请稍后手动再试'}
        print('接口测试未通过：HTTP', exc.code, hints.get(exc.code, '请核对模型名称及服务状态'))
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError):
        print('接口测试未通过：连接或超时问题，请检查网络后再试。')
        sys.exit(1)
    except APIResponseError as exc:
        print('接口测试未通过：' + str(exc))
        sys.exit(1)
    except (ValueError, KeyError, TypeError):
        print('接口测试未通过：响应或工具参数未满足检查规则。')
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\n已取消输入。')
        sys.exit(2)
