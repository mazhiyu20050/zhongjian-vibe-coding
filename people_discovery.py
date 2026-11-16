"""Read-only public person lookup and quarantined Markdown downloads, never remote code execution."""
import base64
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import ssl
import truststore
import time
import urllib.error
from presentation import simplified

USER_AGENT='Zhongjian/0.2 (person identity and public skill discovery)'
PUBLIC_HOSTS=('www.wikidata.org','api.github.com','zh.wikipedia.org','en.wikipedia.org','raw.githubusercontent.com')


def registered_skill(person,folder):
    """A reviewed source location avoids anonymous search API quotas; text only."""
    if person['wikidata_id']!='Q9000717':return None
    base='https://raw.githubusercontent.com/nuwa-skills/leijun-skill/master/'
    opener=urllib.request.build_opener(PublicRedirect(),urllib.request.HTTPSHandler(context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
    files={}
    for name in ('SKILL.md','LICENSE'):
        url=base+name;validate_url(url)
        with opener.open(urllib.request.Request(url,headers={'User-Agent':USER_AGENT}),timeout=8) as response:
            raw=response.read(120001)
        if not raw or len(raw)>120000:raise ValueError('remote_document_too_large')
        files[name]=raw
    text=files['SKILL.md'].decode('utf-8-sig');license_text=files['LICENSE'].decode('utf-8-sig')
    if '雷军' not in simplified(text) or not license_text.startswith('MIT License') or 'Permission is hereby granted' not in license_text:
        raise ValueError('registered_source_mismatch')
    raw=files['SKILL.md'];digest=hashlib.sha256(raw).hexdigest()
    dest=Path(folder)/person['wikidata_id']/digest[:16];dest.mkdir(parents=True,exist_ok=True)
    for name,content in files.items():(dest/name).write_bytes(content)
    metadata={'repository':'https://github.com/nuwa-skills/leijun-skill','ref':'master','path':'SKILL.md','license':'MIT',
              'sha256':digest,'license_sha256':hashlib.sha256(files['LICENSE']).hexdigest(),
              'person':person,'status':'downloaded_pending_review','active':False,
              'note':'第三方人物 Skill 候选；已下载许可证，未执行脚本，待资料审核。'}
    (dest/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata


class PublicAPIError(ConnectionError):
    def __init__(self,kind,service='',retry_after=0,retryable=True):
        super().__init__(kind)
        self.kind=kind;self.service=service;self.retry_after=max(0,retry_after);self.retryable=retryable


def http_failure(error,url):
    service='GitHub' if urllib.parse.urlsplit(url).hostname=='api.github.com' else '人物库'
    headers=error.headers or {}
    limited=error.code==429 or error.code==403 and (headers.get('X-RateLimit-Remaining')=='0' or 'rate limit' in str(error.reason).lower())
    if limited:
        waits=[60]
        for value,epoch in ((headers.get('Retry-After'),False),(headers.get('X-RateLimit-Reset'),True)):
            try:waits.append(max(1,float(value)-(time.time() if epoch else 0)))
            except (TypeError,ValueError):pass
        return PublicAPIError('rate_limited',service,max(waits))
    if error.code in (401,403):return PublicAPIError('access_denied',service,retryable=False)
    return PublicAPIError('service_unavailable',service,8)


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def validate_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in PUBLIC_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('untrusted_public_api')


def public_json(url,maximum=2000000):
    validate_url(url)
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    opener=urllib.request.build_opener(PublicRedirect(),urllib.request.HTTPSHandler(context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
    for attempt in range(2):
        try:
            with opener.open(request,timeout=8) as response:raw=response.read(maximum+1)
            if len(raw)>maximum:raise ValueError('remote_document_too_large')
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code==404:error.close();raise
            failure=http_failure(error,url);error.close()
            if failure.kind in ('rate_limited','access_denied') or attempt:raise failure from None
        except (urllib.error.URLError,TimeoutError,ConnectionError) as error:
            reason=getattr(error,'reason',error)
            if isinstance(reason,ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(reason):
                raise PublicAPIError('certificate_error',retryable=False) from None
            if attempt:
                kind='timeout' if isinstance(reason,(TimeoutError,)) else 'connection_error'
                raise PublicAPIError(kind,retry_after=5) from None
        time.sleep(.4)


def wikidata(params):
    return public_json('https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'format':'json',**params}))


def search_people(query):
    if not isinstance(query,str) or not 1<=len(query.strip())<=80:raise ValueError('invalid_person_search')
    query=simplified(query.strip());errors=[];candidates={}
    for language in ('zh','en'):
        try:
            result=wikidata({'action':'wbsearchentities','search':query,'language':language,'uselang':'zh','limit':8})
            for item in result.get('search',[]):
                if re.fullmatch(r'Q[1-9][0-9]{0,12}',item.get('id','')):candidates[item['id']]=item
            people=verify_candidates(candidates,query)
            if people:return people
        except PublicAPIError as error:
            if error.kind=='rate_limited':raise
            errors.append(error)
        except (OSError,ValueError) as error:errors.append(error)
    # A Wikipedia title/redirect can find entries absent from Chinese Wikidata labels.
    for language in ('zh','en'):
        try:
            params={'action':'query','generator':'search','gsrsearch':query,'gsrlimit':5,'prop':'pageprops','ppprop':'wikibase_item','format':'json'}
            data=public_json('https://'+language+'.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params))
            for page in data.get('query',{}).get('pages',{}).values():
                qid=page.get('pageprops',{}).get('wikibase_item','')
                if re.fullmatch(r'Q[1-9][0-9]{0,12}',qid):candidates[qid]={'label':page.get('title',query)}
            people=verify_candidates(candidates,query)
            if people:return people
        except (OSError,ValueError) as error:errors.append(error)
    if errors:raise errors[0]
    return []


def verify_candidates(candidates,query):
    if not candidates:return []
    # One batch request replaces N sequential P31 requests; retain identity evidence.
    result=wikidata({'action':'wbgetentities','ids':'|'.join(list(candidates)[:12]),
                     'props':'claims|labels|aliases|descriptions|sitelinks','languages':'zh|zh-hans|zh-hant|en','languagefallback':1})
    people=[]
    for qid,entity in result.get('entities',{}).items():
        if qid not in candidates:continue
        human=any(c.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')=='Q5' for c in entity.get('claims',{}).get('P31',[]))
        if not human:continue
        labels=entity.get('labels',{});descriptions=entity.get('descriptions',{})
        claims=entity.get('claims',{})
        def claim_value(key):
            return next((c['mainsnak']['datavalue']['value'] for c in claims.get(key,[])
                         if c.get('rank')!='deprecated' and 'datavalue' in c.get('mainsnak',{})),None)
        def year(key):
            value=claim_value(key)
            if not isinstance(value,dict) or value.get('precision',0)<9:return ''
            match=re.match(r'([+-])(\d{4,6})-',value.get('time',''))
            if not match:return ''
            number=int(match[2]);return ('前' if match[1]=='-' else '')+str(number) if number else ''
        born,died=year('P569'),year('P570')
        photo=claim_value('P18')
        article=entity.get('sitelinks',{}).get('zhwiki',{}).get('title','')
        name=next((labels[k]['value'] for k in ('zh-hans','zh','zh-hant','en') if k in labels),candidates[qid].get('label',query))
        names=[name]+[v['value'] for v in labels.values()]+[a['value'] for values in entity.get('aliases',{}).values() for a in values]
        names=list(dict.fromkeys(simplified(n) for n in names if isinstance(n,str) and len(n)<=100))[:24]
        people.append({'wikidata_id':qid,'person':simplified(name),'description':simplified(next((descriptions[k]['value'] for k in ('zh-hans','zh','zh-hant','en') if k in descriptions),'')),
                       'aliases':names,'identity_url':'https://www.wikidata.org/wiki/'+qid,'verified_human':True,
                       'lifespan':(born+'–'+died if died else born+'年生') if born else '',
                       'portrait_file':photo[:250] if isinstance(photo,str) else '',
                       'zh_article':article[:200] if isinstance(article,str) else '',
                       'verification':'Wikidata P31=Q5','verified_at':int(time.time()),
                       'sitelink_count':len(entity.get('sitelinks',{})),
                       'search_rank':list(candidates).index(qid)})
    return rank_people(people,query)[:5]


def rank_people(people,query):
    """Deterministic best effort, not a claim of certain identity.

    Exact name/alias first, then public encyclopedia coverage, then the search
    provider's relevance order. Download one candidate, never execute its text.
    """
    normalize=lambda s:re.sub(r'[\W_]+','',simplified(s).casefold())
    wanted=normalize(query)
    def score(pair):
        index,person=pair
        exact=2 if normalize(person.get('person',''))==wanted else int(any(normalize(n)==wanted for n in person.get('aliases',[])))
        coverage=person.get('sitelink_count',0)
        coverage=coverage if type(coverage) is int else 0
        return (-exact,-coverage,person.get('search_rank',index),index)
    verified=[p for p in people if p.get('verified_human') and re.fullmatch(r'Q[1-9][0-9]{0,12}',p.get('wikidata_id',''))]
    return [person for index,person in sorted(enumerate(verified),key=score)]


def discover_skill(person,folder):
    """Download a text-only candidate after a human was verified. Quarantine != activation."""
    if not person.get('verified_human') or not re.fullmatch(r'Q[1-9][0-9]{0,12}',person.get('wikidata_id','')):
        raise ValueError('person_not_verified')
    # Reuse only complete, hash-checked text downloads; identity is still
    # independently verified before this function is called.
    for metadata_path in list((Path(folder)/person['wikidata_id']).glob('*/provenance.json'))[:12]:
        try:
            metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
            raw=(metadata_path.parent/'SKILL.md').read_bytes()
            if (len(raw)<=120000 and hashlib.sha256(raw).hexdigest()==metadata.get('sha256')
                and metadata.get('status')=='downloaded_pending_review' and metadata.get('active') is False
                and metadata.get('person',{}).get('wikidata_id')==person['wikidata_id']):
                return {**metadata,'cached':True}
        except (OSError,ValueError,KeyError):continue
    registered=registered_skill(person,folder)
    if registered:return registered
    # Search both display name and romanized/English labels; many repositories
    # advertise only a slug, or keep SKILL.md under skills/<name>/.
    names=list(dict.fromkeys([person['person'],*person.get('aliases',[])]))
    ascii_name=next((n for n in names if re.fullmatch(r'[A-Za-z .\-]{3,80}',n)),None)
    queries=[]
    if ascii_name:queries.append(re.sub(r'[^a-z0-9]','',ascii_name.casefold())+' skill in:name')
    queries.append(person['person']+' skill in:name,description')
    repositories={};search_errors=[]
    for query in queries:
        try:
            result=public_json('https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':query,'per_page':6}))
            for repo in result.get('items',[]):repositories[repo.get('full_name','')]=repo
            if any((r.get('license') or {}).get('spdx_id') in ('MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause','CC0-1.0') for r in repositories.values()):break
        except PublicAPIError as error:
            if error.kind=='rate_limited':raise
            search_errors.append(error)
        except OSError as error:search_errors.append(error)
    if not repositories and search_errors:raise search_errors[0]
    download_errors=[];deadline=time.monotonic()+90
    slugs=[re.sub(r'[^a-z0-9]','',n.casefold()) for n in names]
    slugs=[s for s in slugs if len(s)>=3]
    ranked=sorted(repositories.values(),key=lambda r:not any(s in re.sub(r'[^a-z0-9]','',r.get('name',r.get('full_name','')).casefold()) for s in slugs))
    for repo in ranked[:10]:
        if time.monotonic()>deadline:raise TimeoutError('skill_lookup_budget')
        full=repo.get('full_name','')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',full):continue
        license_id=(repo.get('license') or {}).get('spdx_id')
        if license_id not in ('MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause','CC0-1.0'):continue
        for path in skill_paths(full,repo,person):
          if time.monotonic()>deadline:raise TimeoutError('skill_lookup_budget')
          try:
            item=public_json('https://api.github.com/repos/'+full+'/contents/'+urllib.parse.quote(path,safe='/'),maximum=450000)
            if item.get('encoding')!='base64' or item.get('size',999999)>120000:continue
            raw=base64.b64decode(item['content'],validate=False)
            text=raw.decode('utf-8-sig')
            # Matching a real name is only a candidate check, not an assertion of authenticity.
            if not any(simplified(n).casefold() in simplified(text).casefold() for n in names if len(n)>=3):continue
            dest=Path(folder)/person['wikidata_id']/hashlib.sha256(raw).hexdigest()[:16]
            dest.mkdir(parents=True,exist_ok=True)
            (dest/'SKILL.md').write_bytes(raw)
            metadata={'repository':'https://github.com/'+full,'path':path,'license':license_id,'git_blob_sha':item.get('sha'),
                      'sha256':hashlib.sha256(raw).hexdigest(),'person':person,'status':'downloaded_pending_review',
                      'active':False,'note':'第三方人物 Skill 候选；未执行脚本，未加入运行提示词或原著库。'}
            (dest/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            return metadata
          except (ValueError,KeyError,UnicodeError):
            continue
          except PublicAPIError as error:
            if error.kind=='rate_limited':raise
            download_errors.append(error)
          except urllib.error.HTTPError as error:
            if error.code!=404:download_errors.append(error)
            error.close()
          except OSError as error:download_errors.append(error)
    if download_errors:raise download_errors[0]
    return {'status':'not_found','active':False,'note':'已核实人物身份，但尚未找到许可明确且名称匹配的 Skill。'}


def skill_paths(full,repo,person):
    yield 'SKILL.md'
    # The recursive tree is metadata only, bounded by public_json's size cap.
    # Do not download arbitrary archives or traverse remote scripts/symlinks.
    branch=repo.get('default_branch')
    if not branch:return
    try:
        tree=public_json('https://api.github.com/repos/'+full+'/git/trees/'+urllib.parse.quote(branch,safe='')+'?recursive=1')
        paths=[t['path'] for t in tree.get('tree',[]) if t.get('type')=='blob' and t.get('mode')=='100644'
               and re.fullmatch(r'[A-Za-z0-9_./\-]{1,240}',t.get('path','')) and '..' not in t['path'].split('/')
               and t['path'].endswith('/SKILL.md')]
        slugs=[re.sub(r'[^a-z0-9]','',n.casefold()) for n in [person['person'],*person.get('aliases',[])]]
        slugs=[s for s in slugs if len(s)>=3]
        paths.sort(key=lambda p:(not any(s in re.sub(r'[^a-z0-9]','',p.casefold()) for s in slugs),len(p)))
        yield from paths[:6]
    except PublicAPIError:raise
    except (OSError,ValueError,KeyError):return
