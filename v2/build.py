#!/usr/bin/env python3
"""Strong-first XMLTV builder. Preview only; never overwrites the live guide.

The Strong M3U (not the supplier guides) is the authoritative stream roster.
No third-party channel is emitted unless it maps to a Strong stream. Credentials
are used in memory only and must never appear in XML, audit output or logs.
"""
import argparse, collections, csv, datetime as dt, gzip, hashlib, html, os, re
import sys, urllib.parse as up, urllib.request as ur, xml.etree.ElementTree as ET
from pathlib import Path

UTC=dt.timezone.utc
DEFAULT_SOURCES={
    'ganjarelease':'https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/refs/heads/main/epg6.xml.gz',
    'canada':'https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz',
    'us_local':'https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz',
    'uk':'https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz',
    'portugal':'https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz',
    'brazil':'https://epgshare01.online/epgshare01/epg_ripper_BR1.xml.gz',
}
# Explicit verified aliases, never cross cities or substitute national broadcasts.
ALIASES={
 'CFPL.ca':'ctv2london.ca','CKVR.ca':'ctv2barrie.ca',
 'CKAL.ca':'citytvcalgary.ca','CJNT.ca':'citytvmontrealqc.ca',
 'CHMI.ca':'citytvwinnipeg.ca','CHWI.ca':'ctv2windsor.ca',
 'CIVT.ca':'ctvvancouver.ca','CICT.ca':'globalcalgary.ca',
 'CITV.ca':'globaledmonton.ca','CKMI.ca':'globalmontreal.ca',
 'CHAN.ca':'globalvancouver.ca',
 **{f'SportTV{i}.pt':f'SPORT.TV{i}.HD.pt' for i in range(1,6)},
 'SportTV6.pt':'Sport.TV.6.HD.pt',
 **{f'ElevenSports{i}.pt':f'DAZN.{i}.pt' for i in range(1,7)},
 'BenficaTV1.pt':'BTV1.HD.pt','BenficaTV.pt':'BTV1.HD.pt',
 'Canal11.pt':'Canal.11.HD.pt',
}
ATTR=re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')
DATE=re.compile(r'^(\d{14})\s*([+-]\d{4})?')
BAD=re.compile(r'(?i)(?:password|username|passwd|access_token|api[_-]?key|secret|session[_-]?id|auth|signature)\s*[=:]')
STREAM=re.compile(r'(?i)/(?:live|movie|series|stream|player_api\.php|get\.php|xmltv\.php)(?:/|$)')
SHOW_TAGS={'title','sub-title','desc','category','episode-num','date','language','orig-language','rating','star-rating','credits','video','audio','subtitles','country','previously-shown','premiere','new','live'}
SPORT=re.compile(r'(?:\b(?:TSN\+|NFL|NHL|NBA|MLB|UFC|PPV|FUBO|DAZN|SPORT\s?TV|SKY SPORTS|EUROSPORT|BOXING|WWE|CHAMPIONS LEAGUE)\b|\bSPORTS?\b)',re.I)

def safe_text(text):
    text=(text or '').strip()
    text=re.sub(r'https?://\S+','[link omitted]',text)
    text=BAD.sub('redacted=',text)
    return text[:5000]

def safe_id(value):
    return bool(value and len(value)<=180 and not re.search(r'[/\\?&#<>\r\n]',value) and not BAD.search(value))

def clean_logo(url, private_host=None):
    try:
        p=up.urlsplit((url or '').strip())
        h=(p.hostname or '').lower()
        if p.scheme not in ('https','http') or not h or p.username or p.password or h==private_host:return ''
        if STREAM.search(up.unquote(p.path)) or BAD.search(up.unquote(url)) or p.port not in (None,80,443):return ''
        # No opaque query tokens of any kind in the public output.
        if p.query:return ''
        return up.urlunsplit((p.scheme,h,p.path,'',''))
    except (ValueError,UnicodeError):return ''

def fetch(source):
    if not source:raise ValueError('missing input')
    if source.startswith(('https://','http://')):
        req=ur.Request(source,headers={'User-Agent':'StrongEPG-RosterFirst/2.0'})
        with ur.urlopen(req,timeout=170) as f:raw=f.read(400_000_001)
    else:raw=Path(source).read_bytes()
    if len(raw)>400_000_000:raise ValueError('input too large')
    if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
    if len(raw)>800_000_000 or b'<!ENTITY' in raw.upper():raise ValueError('invalid XML input')
    return raw

def xml(source):
    root=ET.fromstring(fetch(source))
    if root.tag!='tv':raise ValueError('source is not XMLTV')
    return root

def parse_time(value):
    m=DATE.match(value or '')
    if not m:return None
    try:
        zone=m.group(2) or '+0000'
        return dt.datetime.strptime(m.group(1)+' '+zone,'%Y%m%d%H%M%S %z').astimezone(UTC)
    except ValueError:return None

def stamp(value):return value.strftime('%Y%m%d%H%M%S +0000')

def normalize(value):
    s=re.sub(r'^\s*(?:CA|US|UK|PT|BR|IE)\s*[:|\-]\s*','',value or '',flags=re.I)
    s=re.sub(r'\b(?:UHD|HEVC|RAW|FHD|HD|SD|4K|8K|VIP)\b','',s,flags=re.I)
    return re.sub(r'[^a-z0-9+]','',s.lower())

def region_from_id(value):
    ext=value.rsplit('.',1)[-1].lower() if '.' in value else ''
    return {'ca':'ca','us':'us','uk':'uk','pt':'pt','br':'br','ie':'uk'}.get(ext,'')

def category(channel_id,name,group=''):
    s=' '.join((channel_id,name,group))
    # Canada and US remain #1 even for sports; other sports and PPV are #2.
    reg=region_from_id(channel_id)
    if not reg:
        p=re.search(r'\b(?:CA|CANADA|US|USA|UNITED STATES|UK|PT|PORTUGAL|BR|BRAZIL)\b',s,re.I)
        if p:reg={'canada':'ca','ca':'ca','usa':'us','us':'us','united states':'us','uk':'uk','pt':'pt','portugal':'pt','br':'br','brazil':'br'}[p.group(0).lower()]
    if reg in ('ca','us'):return '1 - Canada/USA'
    if reg=='uk' or SPORT.search(s):return '2 - UK/sports/PPV'
    if reg in ('pt','br'):return '3 - Portugal/Brazil'
    return '4 - Other Strong channels'

def catalog(root,private_host):
    data={}
    for ch in root.findall('channel'):
        cid=ch.get('id','')
        if not safe_id(cid):continue
        obj=data.setdefault(cid,{'names':[],'logo':''})
        for n in ch.findall('display-name'):
            s=safe_text(n.text)
            if s and s not in obj['names']:obj['names'].append(s)
        if not obj['logo']:
            for icon in ch.findall('icon'):
                url=clean_logo(icon.get('src'),private_host)
                if url:obj['logo']=url;break
    return data

def load_roster(primary, m3u, private_host):
    """Returns Strong-only channel IDs and a record per stream, with no stream URLs retained."""
    base=catalog(primary,private_host)
    if not m3u:
        return {k:dict(v,group='',mode='Strong XML only') for k,v in base.items()},[],False
    text=fetch(m3u).decode('utf-8-sig','replace')
    if not text.lstrip().startswith('#EXTM3U'):raise ValueError('playlist is not M3U')
    roster={}; streams=[]
    for line in text.splitlines():
        if not line.startswith('#EXTINF:'):continue
        header,title=(line.split(',',1)+[''])[:2]
        attrs=dict(ATTR.findall(header))
        # The text after the comma often carries live event names that tvg-name omits.
        # Keep both as matching aliases, without retaining the stream URL.
        name=safe_text(title or attrs.get('tvg-name'))
        tvg_name=safe_text(attrs.get('tvg-name',''))
        cid=attrs.get('tvg-id','').strip();group=safe_text(attrs.get('group-title',''))
        if not name:continue
        missing=False
        if not safe_id(cid):
            missing=True
            # Stable across updates, but apps may require manual assignment for it.
            key=(group+'\x00'+name).encode('utf-8')
            cid='strong-unmapped-'+hashlib.sha256(key).hexdigest()[:14]
        record=roster.setdefault(cid,{'names':[],'logo':'','group':group,'mode':'Strong playlist'})
        if name not in record['names']:record['names'].append(name)
        if tvg_name and tvg_name not in record['names']:record['names'].append(tvg_name)
        logo=clean_logo(attrs.get('tvg-logo',''),private_host)
        if logo and not record['logo']:record['logo']=logo
        if not record['logo'] and cid in base:record['logo']=base[cid]['logo']
        streams.append({'id':cid,'name':name,'group':group,'manual':missing})
    if not streams:raise ValueError('M3U contained no channels')
    return roster,streams,True

def load_mappings(path):
    mapping={}
    if path and Path(path).exists():
        with open(path,encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                cid=row.get('strong_id','').strip();dest=row.get('secondary_id','').strip()
                if safe_id(cid) and safe_id(dest):mapping[cid]=dest
    mapping.update({k:v for k,v in ALIASES.items() if k not in mapping})
    return mapping

def event_key(value):
    """Only explicit numbered event-channel labels are eligible for auto matching."""
    patterns=[
      r'(TSN\+\s*0*\d{1,3})',
      r'(NFL\s*[|:]\s*0*\d{1,3})',
      r'(DAZN\s*0*\d{1,3}\s*PPV)',
      r'(FUBO\s*(?:SPORTS)?\s*0*\d{1,3})',
      r'(LIVE\s+EVENT\s*0*\d{1,3})',
      r'(BOXING\s*0*\d{1,3})',
    ]
    for p in patterns:
        m=re.search(p,value,re.I)
        if m:return normalize(m.group(1))
    return ''

def stale_event(value,now):
    m=re.search(r'@\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:\b|\s)',value,re.I)
    if not m:return False
    ds=[]
    for y in (now.year-1,now.year,now.year+1):
        try:ds.append(dt.datetime.strptime(f'{y} {m.group(1)} {m.group(2)}','%Y %b %d').replace(tzinfo=UTC))
        except ValueError:pass
    return bool(ds and min(ds,key=lambda d:abs(d-now))+dt.timedelta(days=2)<now)

def matching(roster,base,other,mapping):
    # Exact ID or curated override. Restrict name matches to region and UNIQUE ID.
    nameindex=collections.defaultdict(set)
    for cid,v in other.items():
        for n in v['names']:
            key=normalize(n)
            if len(key)>=6:nameindex[(region_from_id(cid),key)].add(cid)
    dummyindex=collections.defaultdict(set)
    for cid,v in other.items():
        if not cid.lower().startswith('dummy-'):continue
        for n in v['names']:
            if not stale_event(n,dt.datetime.now(UTC)):
                key=event_key(n)
                if key:dummyindex[key].add(cid)
    pairs={};reasons={}
    for cid,entry in roster.items():
        dest='';why=''
        if cid in other:dest=cid;why='exact ID'
        elif cid in mapping and mapping[cid] in other:dest=mapping[cid];why='explicit alias'
        else:
            region=region_from_id(cid)
            if region:
                matches=set().union(*(nameindex.get((region,normalize(n)),set()) for n in entry['names']))
                if len(matches)==1:dest=matches.pop();why='unique same-country name'
            if not dest:
                candidates=set().union(*(dummyindex.get(event_key(n),set()) for n in entry['names'] if event_key(n)))
                if len(candidates)==1:dest=candidates.pop();why='unique numbered sports-event match'
        if dest:pairs[cid]=dest
        reasons[cid]=why or 'not matched'
    return pairs,reasons

def select_sources(ident,entry,sources,pairs):
    # Higher priority first; independent of original provider's channel ID.
    cat=category(ident,entry['names'][0] if entry['names'] else '',entry['group'])
    if cat.startswith('1'):order=('canada','us_local','strong','ganjarelease') if region_from_id(ident)=='ca' else ('us_local','ganjarelease','strong','canada')
    elif cat.startswith('2'):order=('uk','ganjarelease','strong','portugal','brazil')
    elif cat.startswith('3'):order=('portugal','brazil','ganjarelease','strong')
    else:order=('ganjarelease','strong','canada','us_local','uk','portugal','brazil')
    ordered=[]
    for label in order:
        if label not in sources:continue
        dest=ident if ident in sources[label]['names'] else pairs.get(label,{}).get(ident)
        if dest and dest in sources[label]['names']:ordered.append((label,dest))
    return ordered,cat

def programme_index(root,ids,now,end):
    ix=collections.defaultdict(list)
    for p in root.findall('programme'):
        cid=p.get('channel','')
        if cid not in ids:continue
        a=parse_time(p.get('start'));b=parse_time(p.get('stop'))
        if not a or not b or a>=b or b<=now or a>=end:continue
        title=safe_text(p.findtext('title'))
        if not title or (cid.lower().startswith('dummy-') and stale_event(title,now)):continue
        ix[cid].append((max(a,now),min(b,end),p))
    for val in ix.values():val.sort(key=lambda x:(x[0],x[1]))
    return ix

def programme_copy(p,channel,start,end):
    q=ET.Element('programme',{'channel':channel,'start':stamp(start),'stop':stamp(end)})
    for elem in p:
        if elem.tag not in SHOW_TAGS:continue
        x=ET.SubElement(q,elem.tag,{k:v for k,v in elem.attrib.items() if k in ('lang','system','type')})
        x.text=safe_text(elem.text)
        for child in elem:
            y=ET.SubElement(x,child.tag);y.text=safe_text(child.text)
    return q

def fallback(channel,start,end,name):
    p=ET.Element('programme',{'channel':channel,'start':stamp(start),'stop':stamp(end)})
    ET.SubElement(p,'title').text=name
    ET.SubElement(p,'desc').text='Channel-name fallback: reliable programme schedule not available.'
    return p

def compose(entries,now,end,channel,name):
    """Resolve overlapping listings in source priority; fill uncovered time with name."""
    # entries: (source rank,start,end,program)
    boundaries={now,end}
    for _,a,b,_ in entries:boundaries.update((a,b))
    times=sorted(boundaries)
    out=[];fallback_hours=0.0;real_hours=0.0;used=set()
    # At a boundary choose the highest-ranked active programme (no invented data).
    ordered=sorted(entries,key=lambda v:(v[0],v[1],-v[2].timestamp()))
    active=collections.defaultdict(list)
    for v in ordered:active[v[1]].append(v)
    chosen=[];present=[]
    # A rolling active set avoids O(events * intervals) rescans of all schedules.
    stopmap=collections.defaultdict(list)
    for v in ordered:stopmap[v[2]].append(v)
    for a,b in zip(times,times[1:]):
        for v in stopmap.get(a,[]):
            if v in present:present.remove(v)
        present.extend(active.get(a,[]))
        best=min(present,key=lambda v:(v[0],v[1]),default=None)
        marker=(best[0],id(best[3])) if best else None
        if chosen and chosen[-1][2]==marker and chosen[-1][1]==a:chosen[-1]=(chosen[-1][0],b,marker,best)
        else:chosen.append((a,b,marker,best))
    for a,b,marker,v in chosen:
        if v is None:out.append(fallback(channel,a,b,name));fallback_hours+=(b-a).total_seconds()/3600
        else:out.append(programme_copy(v[3],channel,a,b));used.add(v[0]);real_hours+=(b-a).total_seconds()/3600
    return out,round(real_hours,2),round(fallback_hours,2),len(used)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--strong',default=os.environ.get('STRONG_EPG_URL',''))
    ap.add_argument('--m3u',default=os.environ.get('STRONG_M3U_URL',''))
    ap.add_argument('--ganjarelease',default=DEFAULT_SOURCES['ganjarelease'])
    for s in ('canada','us_local','uk','portugal','brazil'):
        ap.add_argument('--'+s.replace('_','-'),default=DEFAULT_SOURCES[s])
    ap.add_argument('--mapping',default='mapping.csv')
    ap.add_argument('--output',default='Strong-preview-v2.xml.gz')
    ap.add_argument('--audit',default='Strong-preview-v2-audit.csv')
    ap.add_argument('--streams',default='Strong-preview-v2-streams.csv')
    ap.add_argument('--now',help='ISO-8601 offset-aware date for reproducible tests')
    ap.add_argument('--require-m3u',action='store_true',help='Fail rather than publish an incomplete Strong XML-only roster')
    args=ap.parse_args()
    if not args.strong:raise ValueError('STRONG_EPG_URL secret or --strong required')
    if args.require_m3u and not args.m3u:raise ValueError('STRONG_M3U_URL required for complete stream coverage')
    now=dt.datetime.fromisoformat(args.now).astimezone(UTC) if args.now else dt.datetime.now(UTC)
    now=now.replace(second=0,microsecond=0);end=now+dt.timedelta(days=7)
    private_host=up.urlsplit(args.strong).hostname
    print('Loading Strong source',flush=True);primary=xml(args.strong)
    print('Reading Strong channel roster',flush=True)
    roster,streams,has_m3u=load_roster(primary,args.m3u,private_host)
    print(f'Strong roster: {len(roster)} unique guide IDs; {len(streams)} playlist streams; complete_playlist={has_m3u}',flush=True)
    sources={'strong':{'root':primary,'names':catalog(primary,private_host)}}
    specs=[('ganjarelease',args.ganjarelease)]+[(s,getattr(args,s)) for s in ('canada','us_local','uk','portugal','brazil')]
    for label,location in specs:
        if not location:continue
        try:
            print('Reading '+label,flush=True);r=xml(location)
            sources[label]={'root':r,'names':catalog(r,private_host)}
            print(f'{label} loaded ({len(sources[label]["names"])} available IDs)',flush=True)
        except Exception as err:
            # Optional providers may fail without taking down other working schedules.
            print(f'{label} not available: {type(err).__name__}',flush=True)
    mapping=load_mappings(args.mapping)
    pairs={};reasons={}
    for label,data in sources.items():
        pairs[label],reasons[label]=matching(roster,None,data['names'],mapping)
    channel_sources={};needed=collections.defaultdict(set)
    for cid,entry in roster.items():
        items,cat=select_sources(cid,entry,sources,pairs)
        channel_sources[cid]=(items,cat)
        for label,source_id in items:needed[label].add(source_id)
    for label,data in sources.items():data['index']=programme_index(data['root'],needed[label],now,end)
    output=ET.Element('tv',{'generator-info-name':'Strong Roster-First EPG v2 preview'})
    audits=[];counts=collections.Counter()
    for cid,v in roster.items():
        c=ET.SubElement(output,'channel',{'id':cid})
        for name in v['names'] or [cid]:ET.SubElement(c,'display-name').text=name
        logo=v['logo']
        if not logo:
            for label,source_id in channel_sources[cid][0]:
                logo=sources[label]['names'][source_id]['logo']
                if logo:break
        if logo:ET.SubElement(c,'icon',{'src':logo});counts['logos']+=1
    for cid,v in roster.items():
        channel_name=v['names'][0] if v['names'] else cid
        ordered,cat=channel_sources[cid]
        schedule=[]
        for rank,(label,source_id) in enumerate(ordered):
            for a,b,p in sources[label]['index'].get(source_id,[]):
                schedule.append((rank,a,b,p))
        blocks,real,missing,used=compose(schedule,now,end,cid,channel_name)
        output.extend(blocks)
        counts[cat]+=1
        if not real:counts['fallback_only']+=1
        audits.append((cid,channel_name,cat,' | '.join(f'{l}:{j}' for l,j in ordered),real,missing,'yes' if v['logo'] else 'from source or missing',v['mode']))
    # Ensure all listings match the Strong roster; zero phantom third-party channels.
    ids=set(roster);ends={}
    for p in output.findall('programme'):
        cid=p.get('channel');a=parse_time(p.get('start'));b=parse_time(p.get('stop'))
        if cid not in ids or a!=ends.get(cid,now) or not b or b<=a:
            raise ValueError('guide validation failed (channel, gap or overlap)')
        ends[cid]=b
    if set(ends)!=ids or any(e!=end for e in ends.values()):raise ValueError('guide has uncovered time')
    raw=ET.tostring(output,encoding='utf-8',xml_declaration=True)
    # Fail closed on secrets. Never print the URL itself.
    if args.strong.startswith(('http://','https://')):
        pieces=up.urlsplit(args.strong)
        vals=[v for k,v in up.parse_qsl(pieces.query) if k.lower() in ('username','password','token','api_key','apikey')]
        for value in vals:
            if value and len(value)>=8 and value.encode() in raw:raise ValueError('private credential in XML')
    if args.m3u.startswith(('http://','https://')):
        if args.m3u.encode() in raw:raise ValueError('private M3U URL in XML')
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(dest,'wb',compresslevel=6) as file:file.write(raw)
    with open(args.audit,'w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['strong_epg_id','display_name','priority','matched_sources','real_schedule_hours','fallback_hours','logo','roster_origin']);w.writerows(audits)
    with open(args.streams,'w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['epg_id','stream_name','group','manual_epg_assignment_needed','streams_sharing_epg_id'])
        per_id=collections.Counter(x['id'] for x in streams)
        w.writerows((x['id'],x['name'],x['group'],'yes' if x['manual'] else 'no',per_id[x['id']]) for x in streams)
    print('Validated preview: roster IDs',len(ids),'programmes',len(output.findall('programme')),'fallback-only IDs',counts['fallback_only'],'priorities:',{k:v for k,v in counts.items() if k.startswith(('1 -','2 -','3 -','4 -'))},flush=True)
    if not has_m3u:print('IMPORTANT: Strong XML-only roster; not a complete IPTV stream inventory. Do not deploy to the public URL yet.',flush=True)
    else:print('Playlist-filtered output, no third-party-only channels.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Avoid leaking secret-bearing exception text in public CI logs.
        print('Build failed: '+type(exc).__name__,file=sys.stderr);sys.exit(1)
