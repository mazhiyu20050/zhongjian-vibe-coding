"""Import three public-domain English editions; Chinese tags are indexes, not quotes."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
from corpus import ROOT, OUTPUT

BOOKS = [(76031,'超越快乐原则','C. J. M. Hubback','1922'),
         (79682,'自我与本我','Joan Riviere','1927'),
         (78221,'文明及其不满','Joan Riviere','1930')]
TERMS = [
    (r'repress|defen[cs]e',['压抑','防御','回避','不愿面对','内心冲突']),
    (r'unconscious',['无意识','潜意识','困惑','真实想法']),
    (r'compulsion to repeat|repetition.compulsion|repetition-compulsion|repeat.*experience', ['重复','关系模式','反复受伤','明知却重蹈覆辙']),
    (r'super.ego|sense of guilt|self.reproach|conscience',['超我','内疚','自责','苛责自己','自我批评']),
    (r'reality.principle|pleasure.principle|postponement',['现实原则','快乐原则','欲望','满足','冲动','取舍']),
    (r'transference|transferred',['移情','期待','亲密关系','熟悉的感觉']),
    (r'anxiety|apprehension|fear',['焦虑','害怕','恐惧']),
    (r'love|loving',['爱情','恋爱','陪伴','失去关系'])]


class Blocks(HTMLParser):
    def __init__(self):
        super().__init__(); self.blocks=[]; self.tag=None; self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if self.skip:
            if tag not in ('br','hr','img','meta','link','input'): self.skip+=1
            return
        if tag in ('script','style','sup') or any(c in attrs.get('class','') for c in ('pagenum','pageno')):
            self.skip=1; return
        if tag in ('p','h1','h2','h3') and not self.tag:
            self.tag=tag; self.parts=[]
    def handle_endtag(self,tag):
        if self.skip:
            self.skip-=1; return
        if tag==self.tag:
            text=re.sub(r'\s+',' ',''.join(self.parts)).strip()
            self.blocks.append((tag,text)); self.tag=None; self.parts=[]
    def handle_data(self,data):
        if self.tag and not self.skip:self.parts.append(data)


def build():
    rows=[]; report=[]
    for number,work,translator,year in BOOKS:
        path=ROOT/'data'/'raw'/'freud'/f'{number}.html'
        raw=path.read_bytes(); parser=Blocks();parser.feed(raw.decode('utf-8-sig'))
        section=None; active=False; count=0
        for tag,text in parser.blocks:
            if tag.startswith('h'):
                if re.match(r'^(?:I|II|III|IV|V|VI|VII|VIII)(?:\s|$)',text):
                    section=text; active=True
                else:
                    active=False
                continue
            if not active or not section or len(text)<35:
                continue
            count+=1
            hints=sorted({term for pattern,terms in TERMS if re.search(pattern,text,re.I) for term in terms})
            rows.append({'id':f'freud-{number}-{count:04d}','kind':'source','person':'弗洛伊德',
                'work':work,'volume':'','section':'第'+section.split()[0]+'章','entry':str(count),
                'section_original':section,'text':text,'language':'en','search_terms':hints,
                'source_url':f'https://www.gutenberg.org/ebooks/{number}',
                'source_file':str(path),'source_sha256':hashlib.sha256(raw).hexdigest(),
                'translator':translator,'edition_year':year,'text_reviewed':False,
                'speaker_note':'弗洛伊德著作的历史英译本，含他人引述；按上下文辨别说话人，中文为AI译意。',
                'quality_warning':'历史理论，不作当代临床结论；网页清洗未逐段人工校对。',
                'attribution':f'Sigmund Freud; translated by {translator}; Project Gutenberg',
                'rights_note':'Project Gutenberg标示美国公有领域；保留历史版本和译者，不使用现代中文译本。',
                'license_url':'https://www.gutenberg.org/policy/license.html'})
        if count<30:raise ValueError('incomplete_book_import')
        report.append({'book':work,'gutenberg_id':number,'paragraphs':count,'sha256':hashlib.sha256(raw).hexdigest(),
            'translator':translator,'edition_year':year,'url':f'https://www.gutenberg.org/ebooks/{number}'})
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'freud.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest={'books':report,'paragraphs':len(rows),'cleaning':'只入正文章节的段落；排除前言、译者说明、索引、脚注区、页码及站点版权尾部；正文保留英译本字符。',
              'display':'中文讲解与英文原句的AI译意分开；英文原句和偏移保留核验。'}
    (OUTPUT/'freud_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
