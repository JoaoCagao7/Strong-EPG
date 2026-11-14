#!/usr/bin/env python3
import urllib.error
import argparse, collections, csv, json, datetime as D, gzip, os, re, sys, urllib.request, urllib.parse as U, ipaddress, xml.etree.ElementTree as E
from pathlib import Path
UTC=D.timezone.utc
SECONDARY='https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/refs/heads/main/epg6.xml.gz'
PORTUGAL='https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz'
PT_MAP={
 **{f'SportTV{n}.pt':f'SPORT.TV{n}.HD.pt' for n in range(1,6)},
 'SportTV6.pt':'Sport.TV.6.HD.pt','SportTV7.pt':'Sport.TV.7.HD.pt',
 'SportTVPlus.pt':'SPORT.TV+.HD.pt','SportTVNBA.pt':'Sport.TV.NBA.pt',
 **{f'ElevenSports{n}.pt':f'DAZN.{n}.pt' for n in range(1,7)},
 **{f'DAZN{n}.pt':f'DAZN.{n}.pt' for n in range(1,7)},
 'BenficaTV1.pt':'BTV1.HD.pt','BenficaTV.pt':'BTV1.HD.pt',
 'Canal11.pt':'Canal.11.HD.pt','SportingTV.pt':'Sporting.TV.HD.pt',
 'Porto.pt':'Porto.Canal.HD.pt','ABolaTV.pt':'A.Bola.TV.HD.pt',
 'Eurosport1.pt':'Eurosport.1.HD.pt','Eurosport2.pt':'Eurosport.2.HD.pt',
 'FuelTV.pt':'Fuel.TV.HD.pt','FightNetwork.pt':'Fight.Network.HD.pt',
}
PT_MAP={k.lower():v for k,v in PT_MAP.items()}
URL=re.compile(r'https?://[^\s<>"\']+',re.I)
CRED=re.compile(r'(?i)(?:username|password|passwd|token|api[_-]?key)\s*=\s*[^\s&<>"\']+')
TAGS={'title','sub-title','desc','category','episode-num','date','language','orig-language','length','rating','star-rating','value','credits','director','actor','writer','producer','presenter','guest','commentator','video','audio','aspect','quality','stereo','previously-shown','premiere','new','live','subtitles','country'}
def clean(s):return CRED.sub('[redacted]',URL.sub('[link removed]',s or '')).strip()
def copy_node(e):
 q=E.Element(e.tag,{k:clean(v) for k,v in e.attrib.items() if k in ('lang','system','units','type')});q.text=clean(e.text)
 for c in e:
  if c.tag in TAGS:q.append(copy_node(c))
 return q
def read(src):
 if src.startswith(('http://','https://')):
  with urllib.request.urlopen(urllib.request.Request(src,headers={'User-Agent':'XMLTV-updater/1.0'}),timeout=180) as r:b=r.read(450000001)
  if len(b)>450000000:raise ValueError('too large')
 else:b=Path(src).read_bytes()
 if b[:2]==b'\x1f\x8b':b=gzip.decompress(b)
 if b'<!ENTITY' in b.upper():raise ValueError('entity declarations')
 root=E.fromstring(b)
 if root.tag!='tv':raise ValueError('not XMLTV')
 return root
def date(s):
 try:return D.datetime.strptime(s,'%Y%m%d%H%M%S %z').astimezone(UTC)
 except (ValueError,TypeError):return None
def stamp(t):return t.strftime('%Y%m%d%H%M%S +0000')
def names(root):
 out={}
 for c in root.findall('channel'):
  i=c.get('id','')
  if not i or URL.search(i) or CRED.search(i):continue
  n=out.setdefault(i,[])
  for x in c.findall('display-name'):
   s=clean(x.text)
   if s and s not in n:n.append(s)
 return out
# Public image references only. No stream paths, account credentials or arbitrary query keys.
IMAGE_QUERY_KEYS={'ver','v','raw','cb','strip','ph','path-prefix','t','pid','resize','auto','ch','h','trim','w','height','width','name','fit','type','style','logo','fallback','q','crop','ixlib','providerId','productId','sourceType','format','size','itok'}
SENSITIVE=re.compile(r'(?i)(?:username|password|passwd|api[_-]?key|access[_-]?token|auth[_-]?token|session[_-]?id|signature|secret|credential|bearer)(?:[=:/?&]|%3d)')
PRIVATE_PATH=re.compile(r'(?i)/(?:live|movie|series|stream|player_api\.php|get\.php|xmltv\.php)(?:/|$)')
def safe_logo(src, blocked_hosts=(), depth=0):
 try:
  if not src or len(src)>5000 or depth>1:return None
  src=src.strip();u=U.urlsplit(src);host=(u.hostname or '').lower().rstrip('.')
  if u.scheme not in ('http','https') or not host or u.username or u.password or host in blocked_hosts or u.port not in (None,80,443):return None
  if '.' not in host or host.endswith(('.local','.localhost','.internal','.lan')):return None
  try:
   ipaddress.ip_address(host);return None  # No raw IP endpoints in the public guide.
  except ValueError:pass
  decoded=U.unquote(U.unquote(src));path=U.unquote(U.unquote(u.path))
  if SENSITIVE.search(decoded) or CRED.search(decoded) or PRIVATE_PATH.search(path) or any(ord(x)<32 for x in decoded):return None
  query=[] if re.fullmatch(r'(?:x)?[0-9]{1,16}',u.query) else U.parse_qsl(u.query,keep_blank_values=True,max_num_fields=25)
  if host=='external-content.duckduckgo.com' and u.path=='/iu/':
   fields=dict(query);target=safe_logo(fields.get('u'),blocked_hosts,depth+1)
   if not target:return None
   # The public proxy's image hash is not a login token; retain only its expected hex format.
   proxy={'u':target,'f':'1','nofb':'1'}
   if re.fullmatch(r'[a-fA-F0-9]{64}',fields.get('ipt','')):proxy['ipt']=fields['ipt']
   return U.urlunsplit(('https',host,'/iu/',U.urlencode(proxy),''))
  if host=='image.mobazzz.com' and u.path=='/':
   return safe_logo(dict(query).get('img'),blocked_hosts,depth+1)
  if host=='github.com':
   match=re.fullmatch(r'/([^/]+)/([^/]+)/blob/([^/]+)/(.*)',u.path)
   if match and all(x not in ('.','..') for x in match.groups()[:3]):
    return U.urlunsplit(('https','raw.githubusercontent.com','/'+ '/'.join(match.groups()),'', ''))
  if any(k not in IMAGE_QUERY_KEYS and not k.startswith('utm_') for k,v in query):return None
  # Cache-busters and campaign tracking are unnecessary for channel artwork.
  query=[(k,v) for k,v in query if k not in ('ver','cb','v') and not k.startswith('utm_')]
  if any('://' in v or len(v)>150 or SENSITIVE.search(v) for k,v in query):return None
  return U.urlunsplit((u.scheme,host,u.path,U.urlencode(query),''))
 except (ValueError,TypeError,UnicodeError):return None

def logo_candidates(root, blocked_hosts):
 result=collections.defaultdict(list)
 for c in root.findall('channel'):
  i=c.get('id','')
  for x in c.findall('icon'):
   url=safe_logo(x.get('src'),blocked_hosts)
   if url and url not in result[i]:result[i].append(url)
 return result

def choose_logo(i,mapped,primary,secondary,method):
 # Source-native IDs stay native, including the secondary dummy/event IDs.
 # Corrected call signs should use the corrected station's artwork, not the bad original ID.
 if method=='callsign correction' and mapped!=i:options=secondary.get(mapped,[])+secondary.get(i,[])+primary.get(i,[])
 else:options=secondary.get(i,[])+primary.get(i,[])+secondary.get(mapped,[])
 return options[0] if options else None

def dummy(i):return i.lower().startswith('dummy-')
def fallback(i,n):
 if dummy(i):
  m=re.search(r'(TSN\+\s*\d+|NFL\s*\|\s*(?:\d+|4k)|BOXING\s*\d+|LIVE EVENT\s*\d+|DAZN\s*\d+|FUBO(?: SPORTS)?\s*\d+)',n,re.I)
  if m:return m[1]
 return n
def stale(p,now):
 m=re.search(r'@\s*([A-Za-z]{3})\s+(\d{1,2})\s+\d{1,2}:\d{2}',p.findtext('title') or '')
 if not m:return False
 ds=[]
 for y in (now.year-1,now.year,now.year+1):
  try:ds.append(D.datetime.strptime(f'{y} {m[1]} {m[2]}','%Y %b %d').replace(tzinfo=UTC))
  except ValueError:pass
 return bool(ds and min(ds,key=lambda x:abs(x-now))+D.timedelta(days=2)<=now)
def norm(n):
 n=re.sub(r'^\s*(?:US|CA(?: EN| FR)?|UK|PT|IE)\s*[:|\-]\s*','',n,flags=re.I)
 n=re.sub(r'\b(?:HD|SD|UHD|FHD|HEVC|4K|RAW|VIP)\b',' ',n,flags=re.I)
 return re.sub(r'[^a-z0-9+]','',n.lower())
def region(i):return i.rsplit('.',1)[-1].lower() if '.' in i else ''
def add(i,a,b,title,desc):
 p=E.Element('programme',channel=i,start=stamp(a),stop=stamp(b));E.SubElement(p,'title').text=title;E.SubElement(p,'desc').text=desc;return p
def nfl_schedule(now, fixture):
 # Use a schedule feed to date provider labels; never assign a game by stream number alone.
 games=[]
 if fixture:
  return json.loads(Path(fixture).read_text())
 try:
  a=(now-D.timedelta(days=1)).strftime('%Y%m%d');b=(now+D.timedelta(days=7)).strftime('%Y%m%d')
  with urllib.request.urlopen('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates='+a+'-'+b+'&limit=100',timeout=30) as f:data=json.load(f)
  for g in data.get('events',[]):
   comp=g['competitions'][0]['competitors'];teams={x['homeAway']:x['team']['name'] for x in comp}
   games.append([teams['away'],teams['home'],g['date']])
 except Exception:print('NFL schedule unavailable; retaining source listings only')
 return games
def verified_nfl(i,ns,games,now,end):
 if not dummy(i):return None
 for n in ns:
  if not re.search(r'\bNFL\s*\|',n,re.I):continue
  for away,home,start in games:
   if not re.search(r'\b'+re.escape(away)+r'\s+at\s+'+re.escape(home)+r'\b',n,re.I):continue
   a=D.datetime.fromisoformat(start.replace('Z','+00:00')).astimezone(UTC);b=a+D.timedelta(hours=4)
   if b<=now or a>=end:continue
   q=add(i,max(a,now),min(b,end),away+' at '+home,'NFL schedule matched to source channel label; end time estimated (four-hour window). Stream availability not independently verified.')
   return max(a,now),min(b,end),q,1
 return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--primary',default=os.getenv('STRONG_EPG_URL'));ap.add_argument('--secondary',default=SECONDARY);ap.add_argument('--portugal',default=PORTUGAL);ap.add_argument('--output',default='Strong-EPG-with-logos.xml.gz');ap.add_argument('--audit',default='coverage.csv');ap.add_argument('--now');ap.add_argument('--nfl-fixture');ap.add_argument('--mapping',default=str(Path(__file__).with_name('mapping.csv')));args=ap.parse_args()
 if not args.primary:raise ValueError('missing primary')
 now=(D.datetime.fromisoformat(args.now).astimezone(UTC) if args.now else D.datetime.now(UTC)).replace(second=0,microsecond=0);end=now+D.timedelta(days=7)
 roots=[]
 for label,source in [('Strong',args.primary),('Ganjarelease',args.secondary)]:
  print('Downloading '+label+' EPG',flush=True)
  try:
   roots.append(read(source.strip()))
  except urllib.error.HTTPError as e:
   print(f'{label}: HTTP status {e.code}',flush=True);raise
  except urllib.error.URLError as e:
   reason=e.reason
   print(f'{label}: connection failed; reason type={type(reason).__name__}; errno={getattr(reason,"errno",None)}',flush=True);raise
  except Exception as e:
   print(f'{label}: {type(e).__name__}',flush=True);raise
  print(label+' EPG loaded',flush=True)
 P,S=map(names,roots)
 # Optional third source: only explicit Portuguese station aliases are used.
 # An outage must not prevent the two-source guide from refreshing.
 pt_root=None;pt_index=collections.defaultdict(list);pt_matches={}
 try:
  print('Downloading Portugal EPG',flush=True)
  pt_root=read(args.portugal.strip());pt_ids=names(pt_root)
  for p in pt_root.findall('programme'):
   i=p.get('channel');a=date(p.get('start'));b=date(p.get('stop'))
   if i not in pt_ids or not a or not b or a>=b or b<=now or a>=end or not clean(p.findtext('title')):continue
   pt_index[i].append((max(a,now),min(b,end),p))
  for items in pt_index.values():items.sort(key=lambda z:(z[0],z[1]))
  print('Portugal EPG loaded; channels with current listings:',len(pt_index),flush=True)
 except Exception as e:
  pt_root=None;pt_index.clear();print('Portugal EPG unavailable; retaining existing sources: '+type(e).__name__,flush=True)
 if not P or not S:raise ValueError('empty source')
 C={i:list(n) for i,n in P.items()}
 for i,ns in S.items():
  dest=C.setdefault(i,[]);dest.extend(n for n in ns if n not in dest)
 for i in C:
  target=PT_MAP.get(i.lower())
  if target and pt_index.get(target):pt_matches[i]=target
 print('Portuguese sports IDs matched:',len(pt_matches),flush=True)
 # Retain original IDs from BOTH sources, including secondary-only dummy channels.
 bycase=collections.defaultdict(set);byname=collections.defaultdict(set)
 for i,ns in S.items():
  if dummy(i):continue
  bycase[i.lower()].add(i)
  if region(i) in ('us','ca','uk','pt','ie'):
   for n in ns:
    if norm(n):byname[region(i),norm(n)].add(i)
 overrides={}
 if Path(args.mapping).exists():
  with open(args.mapping,encoding='utf-8-sig') as f:
   for row in csv.DictReader(f):
    if row['secondary_id'] and row['secondary_id'] in S:overrides[row['strong_id']]=(row['secondary_id'],row['match_method'])
 M={};methods={}
 for i,ns in P.items():
  options=bycase.get(i.lower(),set());t=None;method='unmatched'
  if i in overrides:t,method=overrides[i]
  elif options:t=i if i in options else sorted(options)[0];method='exact/case ID'
  else:
   opts=set().union(*(byname.get((region(i),norm(n)),set()) for n in ns)) if ns else set()
   if len(opts)==1:t=next(iter(opts));method='unique same-country name'
  if t:M[i]=t
  methods[i]=method
 ix=[collections.defaultdict(list),collections.defaultdict(list)];skipped=0
 for k,root in enumerate(roots):
  for p in root.findall('programme'):
   i=p.get('channel');a=date(p.get('start'));b=date(p.get('stop'))
   if i not in C or not a or not b or a>=b or b<=now or a>=end or not clean(p.findtext('title')):continue
   if k==1 and dummy(i) and stale(p,now):skipped+=1;continue
   ix[k][i].append((max(a,now),min(b,end),p))
 if not ix[0] or not ix[1]:raise ValueError('stale or empty source')
 for x in ix:
  for items in x.values():items.sort(key=lambda z:(z[0],z[1]))
 games=nfl_schedule(now,args.nfl_fixture);out=E.Element('tv',{'generator-info-name':'Strong combined XMLTV'});audit=[];counts=collections.Counter()
 blocked={U.urlsplit(x).hostname.lower() for x in (args.primary,os.getenv('STRONG_EPG_URL','')) if U.urlsplit(x).hostname}
 # Never publish logos hosted on the authenticated upstream endpoint.
 primary_logos,secondary_logos=[logo_candidates(r,blocked) for r in roots]
 logos={i:choose_logo(i,M.get(i,i),primary_logos,secondary_logos,methods.get(i)) for i in C}
 # A provider logo with no public candidate is left unset, rather than leaking access tokens or inventing branding.
 for i,ns in C.items():
  c=E.SubElement(out,'channel',id=i)
  for n in ns or [i]:E.SubElement(c,'display-name').text=n
  if logos[i]:E.SubElement(c,'icon',src=logos[i]);counts['channel IDs with logo']+=1
  else:counts['channel IDs without safe logo']+=1
 for i,ns in C.items():
  t=M.get(i,i);selected=[]
  verified=verified_nfl(i,ns,games,now,end)
  if verified:selected.append(verified);counts['NFL verified matchup windows']+=1
  sources=[(0,i),(1,i)]+([(1,t)] if t!=i else [])
  if methods.get(i)=='callsign correction' and t!=i:sources=[(1,t)]
  if i in pt_matches:sources=[(2,pt_matches[i])]+sources
  for k,j in sources:
   # A verified NFL event supersedes the synthetic repeating labels on its stream.
   if verified:continue
   for a,b,p in (pt_index if k==2 else ix[k]).get(j,[]):
    if any(a<y and b>x for x,y,_,_ in selected):continue
    selected.append((a,b,p,k))
  cursor=now;hours=0;source_counts=[0,0,0];n=fallback(i,ns[0] if ns else i)
  for a,b,p,k in sorted(selected,key=lambda x:x[0]):
   if a>cursor:out.append(add(i,cursor,a,n,'Channel name placeholder; schedule unavailable.'));counts['fallback']+=1
   q=E.Element('programme',channel=i,start=stamp(a),stop=stamp(b))
   for child in p:
    if child.tag in TAGS:q.append(copy_node(child))
   if dummy(i):
    desc=q.find('desc')
    if desc is None:desc=E.SubElement(q,'desc')
    desc.text=((desc.text or '')+' Source-supplied label; event time and availability not independently verified.').strip()
   out.append(q);cursor=b;hours+=(b-a).total_seconds()/3600;source_counts[k]+=1;counts['dummy entries' if dummy(i) else 'regular entries']+=1
  if cursor<end:out.append(add(i,cursor,end,n,'Channel name placeholder; schedule unavailable.'));counts['fallback']+=1
  counts['channels with source entries' if selected else 'fallback-only channels']+=1
  audit.append([i,' | '.join(ns),pt_matches.get(i,M.get(i,'')),('Portugal sports explicit ID' if i in pt_matches else methods.get(i,'secondary native')),*source_counts,round(hours,2),round(168-hours,2), 'yes' if logos[i] else 'no'])
 # Verify complete contiguous coverage and all references.
 ends={}
 for p in out.iter('programme'):
  i=p.get('channel');a=date(p.get('start'));b=date(p.get('stop'))
  if i not in C or a!=ends.get(i,now) or not b or b<=a:raise ValueError('coverage validation failed')
  ends[i]=b
 if set(ends)!=set(C) or any(v!=end for v in ends.values()):raise ValueError('incomplete coverage')
 raw=E.tostring(out,encoding='utf-8',xml_declaration=True)
 if CRED.search(raw.decode()):raise ValueError('credential-like text')
 for c in out.findall('channel'):
  for icon in c.findall('icon'):
   if safe_logo(icon.get('src'),blocked) != icon.get('src'):raise ValueError('unsafe logo reference')
 secret=os.getenv('STRONG_EPG_URL') or (args.primary if args.primary.startswith(('http://','https://')) else '')
 if secret:
  parts=U.urlsplit(secret);secrets=[parts.username,parts.password]+[v for k,v in U.parse_qsl(parts.query) if k.lower() in ('username','password','passwd','token','api_key','apikey','access_token')]
  if secret.encode() in raw:raise ValueError('secret in output')
  # Short values can occur naturally in programme titles; compare complete URL components for these.
  for url in logos.values():
   if not url:continue
   text=U.unquote(U.unquote(url))
   if any(v and ((len(v)>=8 and v in text) or re.search(r'(?<![A-Za-z0-9])'+re.escape(v)+r'(?![A-Za-z0-9])',text)) for v in secrets):raise ValueError('credential-like logo URL')
 dest=Path(args.output);tmp=dest.with_name(dest.name+'.tmp')
 with gzip.open(tmp,'wb',compresslevel=6) as f:f.write(raw)
 tmp.replace(dest)
 with open(args.audit,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['channel_id','names','matched_secondary','method','primary_entries','secondary_entries','portugal_entries','source_hours','fallback_hours','logo_present']);w.writerows(audit)
 print('Primary IDs:',len(P),'Secondary IDs:',len(S),'Union:',len(C),'Dummy IDs:',sum(map(dummy,C)),'Expired explicitly dated dummy blocks omitted:',skipped,'Counts:',dict(counts),'Complete coverage validated.')
if __name__=='__main__':
 try:main()
 except Exception as e:print('Build failed: '+type(e).__name__,file=sys.stderr);sys.exit(1)
