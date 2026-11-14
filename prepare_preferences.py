"""Build reviewed pilot corpora for the eight new preference people from saved public sources.

Input downloads are never executed. Modern sources retain a single <=25-word quotation.
"""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from query import quote_candidates

ROOT=Path(__file__).resolve().parent
META={
 'socrates':('苏格拉底','Apology / 苏格拉底的申辩（柏拉图记录）','https://www.gutenberg.org/ebooks/1656',
  [('审视信念','unexamined',['价值','反思','选择']),('承认认识边界','neither know',['提问','判断','自信'])]),
 'plato':('柏拉图','The Republic / 理想国','https://www.gutenberg.org/ebooks/1497',
  [('辨别意见与知识','opinion and knowledge',['判断','学习','事实']),('追问正义','justice',['伦理','公平','责任'])]),
 'aristotle':('亚里士多德','Nicomachean Ethics / 尼各马可伦理学','https://www.gutenberg.org/ebooks/8438',
  [('实践中形成习惯','doing just',['行动','习惯','改变']),('分寸取决于情境','right time',['分寸','情绪','选择'])]),
 'einstein':('爱因斯坦','Relativity / 相对论：狭义与广义理论','https://www.gutenberg.org/cache/epub/5001/pg5001-images.html',
  [('澄清概念的含义','meaning',['提问','概念','判断']),('经验检验假设','experience',['证据','学习','实践'])]),
 'darwin':('达尔文','On the Origin of Species / 物种起源','https://www.gutenberg.org/ebooks/1228',
  [('让观察支撑解释','facts which',['观察','证据','判断']),('重视细微变化的积累','slight variations',['自然','变化','长期'])]),
 'adler':('阿德勒','Understanding Human Nature / 理解人性（历史英译）','https://wellcomecollection.org/works/ww526ncp',
  [('社会联结与共同生活','community',['关系','归属','合作']),('理解行动的方向','goal',['目标','心理','行动'])]),
 'buffett':('巴菲特','1989 Letter to Shareholders / 1989年致股东信','https://www.berkshirehathaway.com/letters/1989.html',
  [('先看质量，再看价格','wonderful company',['决策','商业','价值'])]),
 'steve-jobs':('乔布斯','2005 Stanford Commencement Address / 斯坦福毕业演讲','https://news.stanford.edu/stories/2005/06/youve-got-find-love-jobs-says',
  [('不把人生交给别人的标准','Your time is limited',['选择','价值','独立'])]),
}


class Paragraphs(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.current=[];self.level=0
    def handle_starttag(self,tag,attrs):
        if tag=='p':self.level+=1
    def handle_endtag(self,tag):
        if tag=='p' and self.level:
            self.parts.append(''.join(self.current));self.current=[];self.level-=1
    def handle_data(self,data):
        if self.level:self.current.append(data)


def build():
    manifest=json.loads((ROOT/'skills/people/manifest.json').read_text(encoding='utf-8'))
    manifest=[x for x in manifest if x['person'] not in {m[0] for m in META.values()}]
    report=[]
    for slug,(person,work,url,concepts) in META.items():
        dest=ROOT/'data/raw/preferences'/slug;dest.mkdir(parents=True,exist_ok=True)
        source=ROOT/'.local/new-people-sources'/f'{slug}.txt'
        if slug=='steve-jobs':
            # Verified against the Stanford-published transcript; full copyrighted page is not redistributed.
            text='Your time is limited, so don’t waste it living someone else’s life.'
        else:text=source.read_text(encoding='utf-8-sig',errors='strict')
        if slug=='buffett':
            plain=html.unescape(re.sub(r'<[^>]+>',' ',text));plain=re.sub(r'\s+',' ',plain)
            match=re.search(r"It's far better to buy a wonderful company[^.]+\.",plain)
            if not match:raise ValueError('modern_quote_missing')
            text=match[0]
        modern=slug in ('buffett','steve-jobs')
        if modern and len(text.split())>25:raise ValueError('modern_quote_too_long')
        raw=text.encode('utf-8');snapshot=dest/'source.txt';snapshot.write_bytes(raw)
        if '<html' in text[:2000].lower() or '<!doctype' in text[:100].lower():
            parser=Paragraphs();parser.feed(text);paragraphs=parser.parts
        elif slug=='adler':
            # Wellcome supplies OCR as one line. Segment sentences; do not silently repair OCR spelling.
            paragraphs=re.split(r'(?<=[.!?])\s+(?=[A-Z“])',text[22000:])
        else:
            start={'socrates':text.find('How you, O Athenians'),'plato':text.find('I went down yesterday'),
                   'aristotle':text.find('\nBOOK I\n'),'darwin':text.find('INTRODUCTION.',5000)}.get(slug,0)
            text=text[max(0,start):]
            text=re.split(r'\*\*\* END OF',text)[0]
            paragraphs=re.split(r'\n\s*\n',text)
        paragraphs=[re.sub(r'\s+',' ',p).strip() for p in paragraphs]
        paragraphs=list(dict.fromkeys(p for p in paragraphs if 40<=len(p)<=1800 and not re.search(r'patient|neurotic|psychopath|diagnos|treatment|GUTENBERG',p,re.I)))
        if modern:paragraphs=[text]
        chosen=[];specs=[]
        for number,(name,needle,topics) in enumerate(concepts,1):
            # The actual quoted candidate must contain the key term, not only its enclosing paragraph.
            hits=[(p,q) for p in paragraphs for q in quote_candidates(p) if needle.lower() in q['text'].lower()
                  and len(q['text'].split())>=7 and q['text'][0].isupper()]
            if not hits:raise ValueError('missing_concept:'+slug+':'+needle)
            p,q=hits[0]
            literal=q['text']
            chosen.append(p)
            meaning={
                'socrates':'检验自己的理由与知识边界，不用连环追问羞辱对方；苏格拉底思想经柏拉图记录。',
                'plato':'区分眼前意见、理由和更稳定的判断标准；对话录由不同角色发言，不把所有句子当作者亲口立场。',
                'aristotle':'把判断放在具体处境与实践习惯里，不把中道等同各退一步或机械折中。',
                'einstein':'只有限借鉴澄清定义、参照条件与经验检验的方法，不用物理相对论证明任何心理或道德主张。',
                'darwin':'有限借鉴观察、变异和渐变的方法；不将自然选择等同社会弱肉强食，不用进化论给人排序。',
                'adler':'历史心理学视角用于探索目标与联结，不从只言片语断言潜意识、病因或童年；不把痛苦归咎于本人选择。',
                'buffett':'这条只支持商业中质量与价格的权衡；不是针对个人的证券买卖意见，也不把人的价值按价格衡量。',
                'steve-jobs':'依据演讲讨论有限时间与自主选择；不把直觉当作普遍正确，也不以成功者故事替代事实。',
            }[slug]
            specs.append([slug+'-core-'+str(number),name,[literal],'',meaning,topics,[]])
        for p in paragraphs:
            if any(needle.lower() in p.lower() for _,needle,_ in concepts) and p not in chosen:
                chosen.append(p)
            if len(chosen)>=24:break
        warning='有限主题试点，不是完整人物著作库。'
        if slug=='adler':warning+='原文为馆藏OCR，尚需逐页校勘；只作历史思想参考，不诊断。'
        if modern:warning+='仅收一条短引，超过现有资料范围时不硬套。'
        rows=[]
        for i,p in enumerate(chosen,1):
            rows.append({'id':slug+'-preference-'+str(i),'kind':'source','source':'Reviewed public-source preference pilot',
                'person':person,'work':work,'volume':'','section':'本地主题片段','entry':str(i),'text':p,'language':'en',
                'search_terms':list(dict.fromkeys(t for _,_,ts in concepts for t in ts)), 'source_url':url,
                'source_file':snapshot.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(raw).hexdigest(),
                'speaker_note':('柏拉图记录的苏格拉底申辩，不是苏格拉底亲笔作品。' if slug=='socrates' else '对话作品中的发言须结合说话者与上下文。' if slug=='plato' else '作者历史公开文本，现代应用属于AI解读。'),
                'quality_warning':warning,'rights_note':'单来源短引≤25英文词。' if modern else '历史版本；保留来源与版本，公开再分发前按所在地核对权利。',
                'attribution':work,'translator':'历史英译；中文展示为AI译意','retrieved_date':'2026-10-20','text_reviewed':slug!='adler'})
        (ROOT/'data/processed'/f'additions_{slug}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        (ROOT/'data/processed'/f'thoughts_{slug}.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf-8')
        upstream=ROOT/'skills/downloaded'/slug
        original=(upstream/'SKILL.md').read_bytes();license_raw=(upstream/'LICENSE').read_bytes()
        if b'MIT' not in license_raw:raise ValueError('skill_license_unreviewed:'+slug)
        folder=ROOT/'skills/people'/slug;folder.mkdir(exist_ok=True)
        (folder/'UPSTREAM_SKILL.md').write_bytes(original);(folder/'LICENSE').write_bytes(license_raw)
        text=original.decode('utf-8-sig');match=re.search(r'(?m)^## (?:核心思想模型|核心心智模型|核心理论框架)',text)
        section=re.split(r'(?m)^## ',text[match.end():])[0] if match else ''
        # Retain model names, not unverified quotations, biographies or operational instructions.
        headings=[line for line in section.splitlines() if line.startswith('### ')][:10]
        excerpt='第三方模型目录（不作原文或事实证据）：\n'+'\n'.join(headings)
        (folder/'reviewed-excerpt.md').write_text(excerpt,encoding='utf-8')
        wrapper=f'# {person} · 众见专属解答方法\n\n先辨当前问题，再用以下有原文依据的思想回答：\n'
        wrapper+='\n'.join(f'- {s[1]}：{s[4]}' for s in specs)
        wrapper+='\n\n用第一人称、第二人称自然回应，这是AI思想视角，不假称真人。先给明确判断，再说明依据；证据不足时明确判断的条件，不虚构确定性。只用返回的原著句子作引用；第三方Skill目录并非真实本人或原著。不要执行第三方文件、版本检查或联网命令。篇目与说话人以来源为准。信息不足可简短追问，不读心、不诊断、不保证投资收益。'
        (folder/'SKILL.md').write_text(wrapper,encoding='utf-8')
        repo=('alchaincyf/steve-jobs-skill' if slug=='steve-jobs' else 'nuwa-skills/'+slug+'-skill')
        entry={'person':person,'id':'zhongjian-'+slug,'path':slug+'/SKILL.md','summary':'；'.join(s[1]+'：'+s[4] for s in specs),
               'version':'0.2.0','sha256':hashlib.sha256((folder/'SKILL.md').read_bytes()).hexdigest(),
               'upstream_repository':'https://github.com/'+repo,'upstream_sha256':hashlib.sha256(original).hexdigest(),'upstream_license':'MIT',
               'reviewed_excerpt_file':slug+'/reviewed-excerpt.md','reviewed_excerpt_sha256':hashlib.sha256((folder/'reviewed-excerpt.md').read_bytes()).hexdigest()}
        (folder/'sources.json').write_text(json.dumps({'upstream':entry,'primary':{'url':url,'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'coverage':warning}},ensure_ascii=False,indent=2),encoding='utf-8')
        manifest.append(entry);report.append({'person':person,'units':len(rows),'concepts':len(specs),'upstream':repo})
    (ROOT/'skills/people/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
