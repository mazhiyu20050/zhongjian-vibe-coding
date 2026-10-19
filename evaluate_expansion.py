"""Opt-in paid API integration smoke test using only synthetic development prompts."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from agent import AgentService
from check_api import complete
from collections_store import CollectionStore
from corpus import load_library

CASES=[
    ('孔子','请用孔子的视角直接给建议：我不同意朋友的观点，又怕争吵，我该怎么表达？'),
    ('苏轼','请用苏轼的视角直接给建议：一次考试失利后，我觉得整个人生都失败了。'),
    ('尼采','请用尼采的视角直接给建议：大家都劝我走同一条路，我该怎样检验自己的选择？'),
    ('马斯克','请用马斯克的视角直接给建议：我想做一个软件项目，但预算少，怕准备不够不敢开始。'),
    ('孙宇晨','请用孙宇晨的视角直接给建议：我学了很多编程课却总不动手，怎样把所学用于项目？'),
]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--output',type=Path,default=Path('reports/expanded-api-smoke.json'));args=parser.parse_args()
    if not args.live:raise SystemExit('Pass --live explicitly; this sends synthetic prompts and quotes to the configured API and may incur fees.')
    key=os.environ.get('DEEPSEEK_API_KEY','');model=os.environ.get('DEEPSEEK_MODEL','deepseek-flash')
    if not key:raise SystemExit('DEEPSEEK_API_KEY is required; never put it in the command or report.')
    report={'date':'2026-10-19','model':model,'synthetic_prompts':True,'cases':[]}
    with tempfile.TemporaryDirectory() as tmp:
        def client(messages,**options):
            return complete(key,model,messages,max_tokens=4096,thinking={'type':'disabled'},response_format={'type':'json_object'},**options)
        service=AgentService(load_library(),CollectionStore(Path(tmp)/'test.sqlite3'),client,skill_routing=True,advice_tendencies=True)
        for person,question in CASES:
            try:
                answer=service.ask(question)['result'];cards=answer['cards'];people=[c['person'] for c in cards]
                passed=people==[person] and all(c.get('tendency_applicable') for c in cards)
                record={'person':person,'passed':passed,'returned_people':people,
                        'tool_trace':answer.get('tool_trace',[]),'source_ids':[c['id'] for c in cards],
                        'tendency_totals':[sum(i['percent'] for i in c['advice_tendency']) if c.get('advice_tendency') else None for c in cards],
                        'note':'Strict quote and Skill checks ran in AgentService; relevance and advice quality still require human review.'}
            except Exception as exc:
                record={'person':person,'passed':False,'error_type':type(exc).__name__,'error_code':getattr(exc,'code','unknown')}
            report['cases'].append(record);print(person,record['passed'],flush=True)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(c['passed'] for c in report['cases']) else 1

if __name__=='__main__':raise SystemExit(main())
