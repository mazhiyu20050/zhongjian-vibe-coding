"""Interpretive frameworks with literal primary-text anchors, not historical impersonation."""
from presentation import simplified
from pathlib import Path
import json
from person_registry import EXPANSION

SPECS = {
 '王阳明': [
  ('wym-heart', '心即理', ['心即理也'], '', '把判断的根基放回诚实的是非之心，不只随外界评价转。不是任性，也不是不查事实。', ['评价','迎合','自我怀疑'], ['wym-conscience','wym-reflection']),
  ('wym-knowing-doing', '知行合一', ['知是行之始','知而不行'], '', '真正的知包含切实的行，不以口头明白代替践履；不是责备能力不足的人。', ['明白却做不到','拖延','改变'], ['wym-practice','wym-conscience']),
  ('wym-conscience', '致良知', ['是非之心','至善之发见'], '大学问', '在具体处境辨别是非轻重，让判断落实到恰当的行动；不把情绪或自责直接当良知。', ['对错','良心','选择'], ['wym-heart','wym-knowing-doing']),
  ('wym-practice', '事上磨炼', ['事上磨'], '', '在实际事务与人际往来中练习，不只在安静时想通；不等于忍受伤害或强行硬扛。', ['关系','开口','实践','情绪'], ['wym-knowing-doing','wym-reflection']),
  ('wym-reflection', '省察克治', ['省察克治','只见得人不是'], '', '辨明自己在具体事情上的念头与行为，不因争胜而只见他人之非；反省不等于把责任全揽给自己。', ['批评','争高低','自省','受辱'], ['wym-conscience','wym-heart']),
  ('wym-oneness', '万物一体之仁', ['天地万物为一体'], '大学问', '关切自己与他人的真实处境，不把他人仅当工具；不是无边界讨好，也不否定陪伴需要。', ['关心','边界','陪伴','关系'], ['wym-conscience','wym-practice'])
 ],
 '毛泽东': [
  ('mao-investigation','调查研究与实事求是',['没有调查','实事求是'],'反对本本主义','从具体情况取得判断，不把印象、权威或书本说法直接当事实；不能用来无端怀疑每个人。',['误会','判断','事实'],['mao-practice','mao-contradiction']),
  ('mao-practice','实践与认识',['再认识','真理的标准只能是社会的实践'],'实践论','让认识从实践中来，再由实践检验修正；不是盲动，也不把一次反馈当最终结论。',['不确定','尝试','选择','行动'],['mao-investigation','mao-contradiction']),
  ('mao-contradiction','矛盾分析',['主要矛盾','主要的矛盾'],'矛盾论','区分不同问题的性质、阶段与主次，找到真正起决定作用的症结，而非给所有处境套一个答案。',['纠结','主次','分类','冲突'],['mao-investigation','mao-priorities']),
  ('mao-criticism','批评与自我批评',['你说得对','不怕别人批评指出'],'为人民服务','看批评是否有道理、是否有利于改正实际问题，不因身份而拒听，也不因声音大就照单全收。',['批评','改错','争执'],['mao-investigation','mao-practice']),
  ('mao-feedback','群众路线与倾听',['从群众中来'],'关于领导方法的若干问题','从实际意见中提炼判断，再回到现实中检验；个人关系只能借鉴倾听反馈，不能照搬组织领导关系。',['倾听','沟通','反馈'],['mao-investigation','mao-practice']),
  ('mao-independence','独立自主',['中国同志了解中国情况'],'反对本本主义','立足自身实际独立判断，学习他人经验而不照搬；不等于拒绝合作或听不进不同意见。',['迎合','依赖权威','独立判断'],['mao-investigation','mao-practice']),
  ('mao-priorities','抓重点与统筹',['中心工作','抓紧'],'党委会的工作方法','围绕中心问题，同时照顾相关条件，避免只忙枝节或只抓一点不顾其余。',['重点','安排','过载'],['mao-contradiction','mao-practice']),
  ('mao-stages','分阶段看长期过程',['阶段'],'论持久战','依据条件与发展阶段安排任务，不把短期进退当作全部结局；军事历史推理只作有限的方法借鉴。',['长期','急于求成','进展'],['mao-contradiction','mao-practice'])
 ],
 '弗洛伊德': [
  ('freud-repression','无意识与压抑',['repression'],'自我与本我','感受与口头理由可能并不完全重合，探索被回避的愿望，但隐藏动机只是待检验的假设，不能读心或诱导记忆。',['无意识','潜意识','压抑','回避','不知道为何难受'],['freud-conflict','freud-guilt']),
  ('freud-conflict','愿望、现实与自我要求的冲突',['represents what we call reason'],'自我与本我','把想要什么、现实允许什么和觉得自己应该怎样分开，情绪矛盾不等于人格缺陷；本我自我超我是历史理论模型。',['纠结','内心冲突','想要又害怕','理性与感性'],['freud-reality','freud-guilt']),
  ('freud-guilt','超我、内疚与苛刻自责',['normal conscious sense of guilt'],'自我与本我','自我惩罚的强度不一定等于实际过错，分清具体责任与对自己的无限苛责；不能从自责直接诊断超我强弱或疾病。',['内疚','自责','苛责自己','完美主义','总觉得自己不够好'],['freud-conflict','freud-repression']),
  ('freud-repetition','重复与移情',['always meets with the same fate'],'超越快乐原则','察看反复关系模式中是否带着熟悉的期待，作为探索线索，不凭重复就断定童年创伤、移情或强迫症。',['重复','关系模式','反复受伤','明知却重蹈覆辙','同一种人'],['freud-repression','freud-love']),
  ('freud-reality','快乐与现实原则',['reality-principle'],'超越快乐原则','承认愿望，同时考虑现实条件、延迟满足与代价；不把欲望等同命令，也不把克制等同否认一切需要。',['冲动','欲望','满足','取舍','克制'],['freud-conflict','freud-love']),
  ('freud-love','亲密需要与失去的脆弱',['never so defenceless'],'文明及其不满','看见亲密关系带来的满足与失去时的脆弱，不因此主张断绝关系，也不把渴望陪伴或失恋当疾病。',['爱情','恋爱','陪伴','害怕失去','依恋'],['freud-repetition','freud-reality'])
 ]}

# Additions are explicit, reviewed project data, never arbitrary directory imports.
for _slug, (_person, _) in EXPANSION.items():
    _path = Path(__file__).resolve().parent / 'data' / 'processed' / f'thoughts_{_slug}.json'
    if _path.exists():
        _specs = json.loads(_path.read_text(encoding='utf-8'))
        if not isinstance(_specs, list) or any(not isinstance(s,list) or len(s)!=7 for s in _specs):
            raise ValueError('invalid_thought_specs')
        SPECS[_person] = _specs

def build_profiles(passages):
    """Only expose a concept if its stated anchor exists in this local corpus."""
    profiles = {}
    for person, specs in SPECS.items():
        pool = [p for p in passages if p['person'] == person]
        concepts = []
        for cid, name, needles, section, meaning, topics, links in specs:
            anchor = None
            for p in pool:
                if section and section not in p['section'] and section not in p['work']:
                    continue
                normalized = (p.get('search_text') or simplified(p['text'])).casefold()
                matched = next((n for n in needles if n.casefold() in normalized), None)
                if not matched:
                    continue
                # Import here to keep corpus/presentation dependencies acyclic.
                from query import quote_candidates
                q = next((q for q in quote_candidates(p['text']) if matched.casefold() in simplified(q['text']).casefold()), None)
                if q:
                    anchor = {'passage_id':p['id'], 'work':p['work'], 'volume':p['volume'],
                              'section':p['section'], 'quote':q['text'], 'start':q['start'], 'end':q['end'],
                              'source_url':p['source_url']}
                    break
            if anchor:
                concepts.append({'id':cid,'name':name,'interpretation':meaning,'topics':topics,
                                 'related_concepts':links,'primary_anchor':anchor})
        if concepts:
            valid = {c['id'] for c in concepts}
            for c in concepts:
                c['related_concepts'] = [x for x in c['related_concepts'] if x in valid]
            profiles[person] = {'person':person,'status':'基于原著的思想导读，并非历史本人发言或对其内心的直接还原',
                                'concepts':concepts}
    return profiles
