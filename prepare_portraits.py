"""Fetch attributed Commons thumbnails for the reviewed person directory.

Development-only asset preparation; no external scripts or portrait synthesis.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import re
import ssl
import urllib.parse
import urllib.request
import truststore
from recommendations import people_catalog
from people_discovery import public_json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'web'/'portraits'


def fetch(url,limit=4000000):
    allowed={'commons.wikimedia.org','upload.wikimedia.org','thumb.wikimedia.org','en.wikipedia.org','commons.m.wikimedia.org'}
    def valid(value):
        p=urllib.parse.urlsplit(value)
        if p.scheme!='https' or p.hostname not in allowed or p.username or p.password or p.port not in (None,443):raise ValueError('untrusted_image_host: '+str(p.hostname))
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            valid(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
    valid(url)
    opener=urllib.request.build_opener(Redirect(),urllib.request.HTTPSHandler(context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
    request=urllib.request.Request(url,headers={'User-Agent':'Zhongjian/0.2 (attributed Commons portraits)'})
    with opener.open(request,timeout=15) as response:raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('portrait_too_large')
    return raw


def clean(value):return html.unescape(re.sub('<[^>]*>','',value or '')).strip()[:2000]


def prepare(person):
    qid=person['wikidata_id'];name=person['person'];cache=OUT/(qid+'.source.json')
    if cache.exists():
        metadata=json.loads(cache.read_text(encoding='utf-8'))
        asset=OUT/Path(metadata['url']).name
        if asset.exists() and hashlib.sha256(asset.read_bytes()).hexdigest()==metadata['sha256']:return name,metadata
    entity_cache=ROOT/'.local'/'portrait-entities.json'
    entities=json.loads(entity_cache.read_text(encoding='utf-8')) if entity_cache.exists() else {}
    if qid not in entities:
        query=urllib.parse.urlencode({'action':'wbgetentities','ids':qid,'props':'claims','format':'json'})
        entity=public_json('https://www.wikidata.org/w/api.php?'+query,maximum=4000000)['entities'][qid]
    else:entity=entities[qid]
    photos=entity.get('claims',{}).get('P18',[])
    if not photos:raise ValueError('portrait_not_available: '+name)
    filename=photos[0]['mainsnak']['datavalue']['value']
    query=urllib.parse.urlencode({'action':'query','titles':'File:'+filename,'prop':'imageinfo',
            'iiprop':'url|extmetadata','iiurlwidth':320,'format':'json'})
    try:data=json.loads(fetch('https://en.wikipedia.org/w/api.php?'+query))
    except OSError:data=json.loads(fetch('https://commons.wikimedia.org/w/api.php?'+query))
    page=next(iter(data['query']['pages'].values()));info=page['imageinfo'][0];ext=info['extmetadata']
    license=clean(ext.get('LicenseShortName',{}).get('value',''))
    if not re.search(r'CC |CC0|public domain|PD|free use',license,re.I):raise ValueError('unreviewed_portrait_license: '+license)
    image_url=info.get('thumburl') or info['url'];raw=fetch(image_url)
    if raw.startswith(b'\xff\xd8\xff'):suffix='.jpg'
    elif raw.startswith(b'\x89PNG\r\n\x1a\n'):suffix='.png'
    elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':suffix='.webp'
    else:raise ValueError('portrait_format_not_supported')
    path=OUT/(qid+suffix);path.write_bytes(raw)
    metadata={'url':'/portraits/'+path.name,'source':info['descriptionurl'],'file':filename,
              'artist':clean(ext.get('Artist',{}).get('value','')),'license':license,
              'license_url':ext.get('LicenseUrl',{}).get('value',''),'sha256':hashlib.sha256(raw).hexdigest(),
              'note':'历史人物使用传世画像或雕像，不宣称是真人照片。'}
    cache.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return name,metadata


def main():
    OUT.mkdir(parents=True,exist_ok=True);manifest={};errors=[]
    cache=ROOT/'.local'/'portrait-entities.json'
    if not cache.exists():
        query=urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(p['wikidata_id'] for p in people_catalog()),'props':'claims','format':'json'})
        try:
            entities=public_json('https://www.wikidata.org/w/api.php?'+query,maximum=12000000)['entities']
            cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(entities,ensure_ascii=False),encoding='utf-8')
        except Exception as error:print('Batch identity cache:',type(error).__name__,flush=True)
    def attempt(person):
        for _ in range(2):
            try:return prepare(person)
            except Exception as error:last=error
        return person['person'],{'error':type(last).__name__+': '+str(last)[:180]}
    with ThreadPoolExecutor(max_workers=1) as pool:
        for name,result in pool.map(attempt,people_catalog()):
            if 'error' in result:errors.append({'person':name,**result})
            else:manifest[name]=result
            print(name,'ok' if 'error' not in result else result['error'],flush=True)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    credits=['<!doctype html><meta charset="utf-8"><title>众见 · 肖像来源</title><h1>肖像来源与许可</h1><p>历史人物使用传世画像或雕像，不宣称是真人照片。</p>']
    for name,p in manifest.items():
        credits.append('<section><h2>'+html.escape(name)+'</h2><p>'+html.escape(p['artist'])+'</p><p>'+html.escape(p['license'])+'</p><a href="'+html.escape(p['source'],quote=True)+'">原始文件、作者与完整许可说明</a></section>')
    (OUT/'credits.html').write_text('\n'.join(credits),encoding='utf-8')
    (ROOT/'reports'/'portraits-preparation.json').write_text(json.dumps({'ready':len(manifest),'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
