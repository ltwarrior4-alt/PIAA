"""Official PIAA District 1 scoring feed synchronizer. Python standard library only.

Important: PIAA District 1 has not advertised a public API; this parser reads the
published standings/schedule HTML and refuses to replace a good snapshot on failure.
No non-PIAA enrollment or out-of-district W-L figures are fabricated.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
from html.parser import HTMLParser
import json, os, pathlib, re, threading, time, urllib.request, urllib.error, unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent
SITE='https://www.piaad1.org'
STANDINGS=SITE+'/sports/fall-sports/football/scores-and-rankings/'
SCHEDULE=SITE+'/index.php/sports/fall-sports/football/scores-and-rankings/games/2026-{}-football'
REFRESH_INTERVAL=15*60
# On a public service, visitors may check for updates, but cannot trigger
# unlimited external scraping jobs. Only one sync starts per interval.

SEED=json.loads((ROOT/'2026_rankings_and_games.json').read_text(encoding='utf-8'))
INDEX={t['name']:t for t in SEED['teams']}
MAIN={t['name'] for t in SEED['teams'] if t['cls']=='6A' and t['officialSeed'] is not None}
# Supplemental score/record feeds for schools outside District 1.
# Public scoreboard pages may lag or reject automated access. Always labeled secondary.
EXTERNAL_SOURCES={
 'Appoquinimink HS (DE)':'https://www.maxpreps.com/de/west-middletown/appoquinimink-jaguars/football/schedule/',
 'Trenton Central HS (NJ)':'https://www.maxpreps.com/nj/trenton/trenton-central-tornadoes/football/schedule/',
 'William Penn HS (DE)':'https://www.maxpreps.com/de/new-castle/william-penn-colonials/football/schedule/',
 'Maret School (DC)':'https://www.maxpreps.com/dc/washington/maret-frogs/football/schedule/',
 'The Seed School (MD)':'https://www.maxpreps.com/md/baltimore/seed/football/schedule/',
 'Archbishop Ryan High School':'https://www.maxpreps.com/pa/philadelphia/archbishop-ryan-raiders-and-ragdolls/football/schedule/',
 'Easton Area High School':'https://www.maxpreps.com/pa/easton/easton-area-red-rovers/football/schedule/',
 'Southern Lehigh High School':'https://www.maxpreps.com/pa/center-valley/southern-lehigh-spartans/football/schedule/',
 'Exeter Township High School':'https://www.maxpreps.com/pa/reading/exeter-township-eagles/football/schedule/',
 'Central York High School':'https://www.maxpreps.com/pa/york/central-york-panthers/football/schedule/',
 'Northeast High School':'https://www.maxpreps.com/pa/philadelphia/northeast-vikings/football/schedule/',
}
EXTERNAL_SOURCES.update({
 'Abraham Lincoln High School':'https://www.maxpreps.com/pa/philadelphia/abraham-lincoln-railsplitters/football/schedule/',
 'Archbishop Wood High School':'https://www.maxpreps.com/pa/warminster/archbishop-wood-vikings/football/schedule/',
 "Boys' Latin of Philadelphia Charter School":'https://www.maxpreps.com/pa/philadelphia/boys-latin-charter-warriors/football/schedule/',
 'Emmaus High School':'https://www.maxpreps.com/pa/emmaus/emmaus-hornets/football/schedule/',
 'Executive Education Academy Charter School (PA)':'https://www.maxpreps.com/pa/allentown/executive-education-academy-charter-school/football/schedule/',
 'Freedom High School':'https://www.maxpreps.com/pa/bethlehem/freedom-patriots/football/schedule/',
 'Governor Mifflin High School':'https://www.maxpreps.com/pa/shillington/governor-mifflin-mustangs/football/schedule/',
 'Liberty High School':'https://www.maxpreps.com/pa/bethlehem/liberty-hurricanes/football/schedule/',
 'Lower Dauphin High School':'https://www.maxpreps.com/pa/hummelstown/lower-dauphin-falcons/football/schedule/',
 'Manheim Township High School':'https://www.maxpreps.com/pa/lancaster/manheim-township-blue-streaks/football/schedule/',
 'Murrell Dobbins CTE High School':'https://www.maxpreps.com/pa/philadelphia/murrell-dobbins-vo-tech/football/schedule/',
 'South Philadelphia High School':'https://www.maxpreps.com/pa/philadelphia/south-philadelphia-rams/football/schedule/',
 'West Philadelphia High School':'https://www.maxpreps.com/pa/philadelphia/west-philadelphia-speedboys/football/schedule/',
 'Wilson High School (D3)':'https://www.maxpreps.com/pa/west-lawn/wilson-bulldogs/football/schedule/',
 'Pickett Mastery Charter':'https://www.maxpreps.com/pa/philadelphia/mastery-charter-north-pickett-pumas/football/schedule/',
})
MAXPREPS_6A={'PENNRIDGE': 'https://www.maxpreps.com/pa/perkasie/pennridge-rams/football/schedule/', 'PLYMOUTH WHITEMARSH': 'https://www.maxpreps.com/pa/plymouth-meeting/plymouth-whitemarsh-colonials/football/schedule/', 'DOWNINGTOWN EAST': 'https://www.maxpreps.com/pa/exton/downingtown-east-cougars/football/schedule/', 'CB WEST': 'https://www.maxpreps.com/pa/doylestown/central-bucks-west-bucks/football/schedule/', 'SPRING-FORD': 'https://www.maxpreps.com/pa/royersford/spring-ford-rams/football/schedule/', 'DOWNINGTOWN WEST': 'https://www.maxpreps.com/pa/downingtown/downingtown-west-whippets/football/schedule/', 'RIDLEY': 'https://www.maxpreps.com/pa/folsom/ridley-raiders/football/schedule/', 'NORTH PENN': 'https://www.maxpreps.com/pa/lansdale/north-penn-knights/football/schedule/', 'CB EAST': 'https://www.maxpreps.com/pa/doylestown/central-bucks-east-patriots/football/schedule/', 'COATESVILLE': 'https://www.maxpreps.com/pa/coatesville/coatesville-red-raiders/football/schedule/', 'OWEN J. ROBERTS': 'https://www.maxpreps.com/pa/pottstown/owen-j-roberts-wildcats/football/schedule/', 'CB SOUTH': 'https://www.maxpreps.com/pa/warrington/central-bucks-south-titans/football/schedule/', 'QUAKERTOWN': 'https://www.maxpreps.com/pa/quakertown/quakertown-panthers/football/schedule/', 'UPPER DARBY': 'https://www.maxpreps.com/pa/drexel-hill/upper-darby-royals/football/schedule/', 'COUNCIL ROCK SOUTH': 'https://www.maxpreps.com/pa/holland/council-rock-south-golden-hawks/football/schedule/', 'NESHAMINY': 'https://www.maxpreps.com/pa/langhorne/neshaminy-skins/football/schedule/', 'PENNSBURY': 'https://www.maxpreps.com/pa/fairless-hills/pennsbury-falcons/football/schedule/', 'HARRY S. TRUMAN': 'https://www.maxpreps.com/pa/levittown/harry-s-truman-tigers/football/schedule/', 'HAVERFORD': 'https://www.maxpreps.com/pa/havertown/haverford-fords/football/schedule/', 'SOUDERTON': 'https://www.maxpreps.com/pa/souderton/souderton-indians/football/schedule/', 'PERKIOMEN VALLEY': 'https://www.maxpreps.com/pa/collegeville/perkiomen-valley-vikings/football/schedule/', 'PENN WOOD': 'https://www.maxpreps.com/pa/lansdowne/penn-wood-patriots/football/schedule/', 'CONESTOGA': 'https://www.maxpreps.com/pa/berwyn/conestoga-pioneers/football/schedule/', 'ABINGTON': 'https://www.maxpreps.com/pa/abington/abington-galloping-ghosts/football/schedule/', 'AVON GROVE': 'https://www.maxpreps.com/pa/west-grove/avon-grove-red-devils/football/schedule/', 'BOYERTOWN': 'https://www.maxpreps.com/pa/boyertown/boyertown-bears/football/schedule/', 'WILLIAM TENNENT': 'https://www.maxpreps.com/pa/warminster/william-tennent-panthers/football/schedule/', 'BENSALEM': 'https://www.maxpreps.com/pa/bensalem/bensalem-fighting-owls/football/schedule/', 'NORRISTOWN': 'https://www.maxpreps.com/pa/norristown/norristown-eagles/football/schedule/', 'COUNCIL ROCK NORTH': 'https://www.maxpreps.com/pa/newtown/council-rock-north-indians/football/schedule/'}
MP_CACHE=ROOT/"maxpreps_schedule_audit.json"
MP_AUDIT_INTERVAL=6*60*60  # separate, lower-frequency check; not needed for score updates

CACHE=ROOT/'live_feed.json' 
lock=threading.Lock()
active=False
last_error=''
last_attempt=None
cached={}

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.depth=0;self.in_row=False;self.cell=False;self.buff=[];self.row=[];self.table=[];self.tables=[]
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            if self.depth==0:self.table=[]
            self.depth+=1
        elif self.depth and tag=='tr': self.in_row=True;self.row=[]
        elif self.depth and self.in_row and tag in ('td','th'): self.cell=True;self.buff=[]
    def handle_data(self,data):
        if self.cell:self.buff.append(data)
    def handle_endtag(self,tag):
        if self.depth and self.in_row and tag in ('td','th') and self.cell:
            self.row.append(re.sub(r'\s+',' ',' '.join(self.buff)).strip());self.cell=False
        elif tag=='tr' and self.in_row:
            if self.row:self.table.append(self.row)
            self.in_row=False
        elif tag=='table' and self.depth:
            self.depth-=1
            if self.depth==0:self.tables.append(self.table)

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.skip=0; self.items=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','svg','noscript'): self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','svg','noscript'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip and data.strip(): self.items.append(data.strip())

def parse_external_record(html,source):
    visible=VisibleText();visible.feed(html)
    txt=re.sub(r'\s+',' ',' '.join(visible.items))
    # MaxPreps must be showing its 2026-27 football schedule, not last season.
    if 'Football' not in txt or not re.search(r'2026\s*[-–]\s*27',txt):
        raise ValueError('not a current 2026-27 football schedule')
    m=re.search(r'\bOverall\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\b',txt,re.I)
    if not m: raise ValueError('record not found on page')
    w,l=map(int,m.groups())
    if w+l>15: raise ValueError('season record implausible')
    stamp=re.search(r'Schedule last updated on\s+(\w+\s+\d{1,2},\s+2026)',txt,re.I)
    freshness=None
    if stamp:
        day=dt.datetime.strptime(stamp.group(1),'%b %d, %Y').date()
        freshness=(dt.datetime.now(dt.timezone.utc).date()-day).days
        if freshness>21:raise ValueError('scoreboard not updated for '+str(freshness)+' days')
    if dt.datetime.now(dt.timezone.utc).date()>dt.date(2026,10,31):
        raise ValueError('overall record can include games after PIAA 10-week season; no auto-import after Oct 31')
    return {'w':w,'l':l,'source':source,'lastScheduleUpdate':stamp.group(1) if stamp else None,
            'status':'secondary-maxpreps','warning':('Source last updated '+str(freshness)+' days ago' if freshness is not None and freshness>7 else None)}

def normalize(s):
    return re.sub(r'[^A-Z0-9]+','',unicodedata.normalize('NFKD',str(s)).upper())
ALIAS={normalize(n):n for n in INDEX}
# Official pages sometimes shorten external opponent labels.
ALIAS.update({normalize('Boys Latin of Philadelphia Charter School'):"Boys' Latin of Philadelphia Charter School",
              normalize('Executive Education Academy Charter School'):'Executive Education Academy Charter School (PA)',
              normalize('Penn (William) High School'):'William Penn HS (DE)',
              normalize('Trenton Central High School'):'Trenton Central HS (NJ)',
              normalize('The Seed School of Maryland'):'The Seed School (MD)'})
def canon(s): return ALIAS.get(normalize(s),str(s).strip())
def to_int(s):
    try:return int(re.sub(r'[^\d-]','',str(s)))
    except:return None

def rows(html):
    p=Tables();p.feed(html);return p.tables

def parse_rankings(html):
    result={}
    for table in rows(html):
        if not any(any('total points' in x.lower() for x in row) for row in table[:5]):continue
        for row in table:
            if len(row)<7:continue
            n=canon(row[1]);w=to_int(row[2]);l=to_int(row[3]);p=int(round(float(row[5].replace(',','')))) if re.fullmatch(r'[0-9,]+(?:\.[0-9]+)?',row[5].strip()) else None
            if n in INDEX and w is not None and l is not None and p is not None:
                result[n]={'w':w,'l':l,'points':p,'seed':to_int(row[0])}
    if len(MAIN & result.keys())!=len(MAIN):
        raise ValueError(f'Incomplete 6A standings: found {len(MAIN & result.keys())}/{len(MAIN)} schools; retaining previous data')
    # A partially cached or out-of-date page must not overwrite a later, valid
    # official snapshot. Compare with BOTH the original seed and the last sync.
    previous=(cached or {}).get('rankings',{})
    seeds=[]
    for n in MAIN:
        now=result[n]; old=previous.get(n, INDEX[n])
        if now['w']+now['l'] < old['w']+old['l']:
            raise ValueError('Ranking games regressed for '+n)
        if now['w']<0 or now['l']<0 or now['w']+now['l']>10 or now['points']<0:
            raise ValueError('Implausible regular-season standings: '+n)
        if now['seed'] is None or not 1<=now['seed']<=len(MAIN):
            raise ValueError('Missing 6A seed for '+n)
        seeds.append(now['seed'])
    if sorted(seeds)!=list(range(1,len(MAIN)+1)):
        raise ValueError('Published 6A seed list is incomplete or contains duplicates')
    return result

def parse_schedule(html,source_team):
    fixtures=[]
    for table in rows(html):
        if not any(any('score' in x.lower() for x in r) for r in table[:4]):continue
        for r in table:
            if len(r)<4:continue
            m=re.fullmatch(r'(\d{1,2})/(\d{1,2})/(2026)',r[0]);
            if not m:continue
            day=f'{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}'
            if not ('2026-08-21'<=day<='2026-10-31'):continue
            home=canon(r[1]);away=canon(r[2]);
            if normalize(source_team) not in (normalize(home),normalize(away)):continue
            if home==away:continue
            score=re.search(r'^\s*(\d{1,3})\s*/\s*(\d{1,3})\s*$',r[3])
            hs,as_=(int(score[1]),int(score[2])) if score else (None,None)
            fixtures.append({'date':day,'home':home,'away':away,'homeScore':hs,'awayScore':as_,'played':score is not None,'scoreSource':SCHEDULE.format(slug(source_team))})
    return fixtures

def slug(team):
    x=team.lower().replace('&','and');return re.sub(r'-+','-',re.sub('[^a-z0-9]+','-',x)).strip('-')


# MaxPreps is a secondary schedule CROSS-CHECK, never the authority for official points.
# Its HTML can change and the site can reject automated access. Parsing failures
# produce explicit source-status entries, rather than assumed missing or added games.
MP_ALIAS={
 'CENTRALBUCKSWEST':'CB WEST','CENTRALBUCKSEAST':'CB EAST','CENTRALBUCKSSOUTH':'CB SOUTH',
 'PWH S':'PLYMOUTH WHITEMARSH','PWHS':'PLYMOUTH WHITEMARSH','CBEHS':'CB EAST',
 'CBWHS':'CB WEST','DWHS':'DOWNINGTOWN WEST','AWHS':'Archbishop Wood High School',
 'HENDERSON':'WC HENDERSON','BAYARDRUSTIN':'WC RUSTIN','EAST':'WC EAST',
 'SEED':'The Seed School (MD)','BOYSLATINCHARTER':"Boys' Latin of Philadelphia Charter School",
 'EEACS':'Executive Education Academy Charter School (PA)',
 'TRENTONCENTRAL':'Trenton Central HS (NJ)',
 'APP0QUINIMINK':'Appoquinimink HS (DE)',
 'WILLIAMPENN':'William Penn HS (DE)',
 'NORTHEAST':'Northeast High School',
 'LIBERTY':'Liberty High School',
 'WILSON':'Wilson High School (D3)',
 'FREEDOM':'Freedom High School',
 'GOVERNORMIFFLIN':'Governor Mifflin High School',
 'EXETERTOWNSHIP':'Exeter Township High School',
 'CENTRALYORK':'Central York High School',
 'LOWERDAUPHIN':'Lower Dauphin High School',
 'EASTONAREA':'Easton Area High School',
 'EMMAUS':'Emmaus High School',
 'SOUTHERNLEHIGH':'Southern Lehigh High School',
 'MANHEIMTOWNSHIP':'Manheim Township High School',
 'MURRELLDOBBINSVOTECH':'Murrell Dobbins CTE High School',
 'ABRAHAMLINCOLN':'Abraham Lincoln High School',
 'ARCHBISHOPRYAN':'Archbishop Ryan High School',
 'ARCHBISHOPWOOD':'Archbishop Wood High School',
 'WESTPHILADELPHIA':'West Philadelphia High School',
 'SOUTHPHILADELPHIA':'South Philadelphia High School',
 'MARET':'Maret School (DC)',
}
for n in INDEX:MP_ALIAS.setdefault(normalize(n),n)
MP_ALIAS.update({normalize(k):v for k,v in {
 'Pope John Paul II':'POPE JOHN PAUL II',
 'Upper Merion Area':'UPPER MERION',
 'Springfield Township':'SPRINGFIELD TWP.(M)',
 'Central Bucks West':'CB WEST', 'Central Bucks East':'CB EAST',
 'Central Bucks South':'CB SOUTH','Haverford':'HAVERFORD',
 }.items()})
# Require a valid football-style time, so the digit directly following the day
# in MaxPreps' compact display (8/287:00pm) cannot be misread as day 2, hour 87.
MP_DATE=re.compile(r'(?<!\d)(?P<month>8|9|10)/(?P<day>3[01]|[12]\d|[1-9])\s*(?P<hour>1[0-2]|0?[1-9]):[0-5]\d\s*(?:am|pm)',re.I)
MP_OPP=re.compile(r'(?:\bvs\s*|@\s*)(?P<opp>.+?)(?=\s+(?:W|L|T)\s+\d{1,3}\s*[-–]|\s+(?:Preview Game|View Matchup|Report Score|Box Score|Buy Tickets|Watch Replay|Watch|Tickets)\b|$)',re.I)

def mp_team(raw,school):
    n=normalize(raw.rstrip(' *'))
    if n=='SPRINGFIELD':return 'SPRINGFIELD (DELCO)' if school in ('RIDLEY','UPPER DARBY','PERKIOMEN VALLEY','CONESTOGA','HAVERFORD') else 'SPRINGFIELD TWP.(M)'
    if not n:return None
    return MP_ALIAS.get(n)

def parse_maxpreps_fixtures(html,team):
    vis=VisibleText();vis.feed(html)
    txt=re.sub(r'\s+',' ',' '.join(vis.items))
    if not re.search(r'(?:2026[-–]27|26[-–]27)',txt) or 'Football Schedule' not in txt:
        raise ValueError('2026–27 football schedule not found')
    start=txt.find('Date/Time')
    if start<0:raise ValueError('schedule table not found')
    stop=txt.find('Schedule last updated',start)
    schedule=txt[start:(stop if stop>start else len(txt))]
    dates=list(MP_DATE.finditer(schedule))
    if not dates:raise ValueError('dated varsity fixtures could not be extracted')
    games=[];unmapped=[];outside=[]
    for i,m in enumerate(dates):
        try:date=dt.date(2026,int(m['month']),int(m['day'])).isoformat()
        except ValueError:continue
        segment=schedule[m.end():dates[i+1].start() if i+1<len(dates) else len(schedule)]
        opp=MP_OPP.search(segment[:350])
        if not opp:continue
        raw=opp['opp'].strip(' *:-');raw=re.sub(r'\s*\*+$','',raw).strip()
        if not raw or raw.upper() in ('TBA','TBA OPPONENT') or re.match(r'TBA\s*\(',raw,re.I):
            unmapped.append({'date':date,'raw':raw or 'TBA','reason':'unannounced opponent'});continue
        other=mp_team(raw,team)
        if date<'2026-08-21' or date>'2026-10-31':
            outside.append({'date':date,'opponent':raw});continue
        if other is None:
            unmapped.append({'date':date,'raw':raw,'reason':'name not mapped'});continue
        if other==team:continue
        side='home' if segment[:opp.start()].strip().startswith('vs') else 'away'
        # Typical MaxPreps 'vs' and '@' text can be concatenated to the team name.
        prefix=segment[:opp.end()]
        if re.search(r'@\s*'+re.escape(raw),prefix,re.I):side='away'
        elif re.search(r'\bvs\s*'+re.escape(raw),prefix,re.I):side='home'
        game={'date':date,'home':team if side=='home' else other,
              'away':other if side=='home' else team,'sourceTeam':team,
              'url':MAXPREPS_6A[team]}
        if not any(unique_fixture_key(g)==unique_fixture_key(game) for g in games):games.append(game)
    if not games:raise ValueError('no identifiable 2026 varsity fixtures')
    updated=re.search(r'Schedule last updated on\s+(\w+\s+\d{1,2},\s*2026)',txt,re.I)
    freshness=None
    if updated:
        try:freshness=(dt.datetime.now(dt.timezone.utc).date()-dt.datetime.strptime(updated[1],'%b %d, %Y').date()).days
        except ValueError:pass
    return {'fixtures':games,'unmapped':unmapped,'outsideWindow':outside,'totalDated':len(dates),
            'lastUpdated':updated.group(1) if updated else None,
            'ageDays':freshness,'stale':freshness is not None and freshness>14}

def schedule_audit(http_get=None,reference=None):
    if http_get is None:http_get=fetch
    existing=list(reference if reference is not None else SEED['games'])
    existing_keys={unique_fixture_key(g) for g in existing}
    by_pair={tuple(sorted((g['home'],g['away']))):g for g in existing}
    statuses={};found=[]
    def worker(item):
        n,url=item
        try:
            parsed=parse_maxpreps_fixtures(http_get(url),n)
            return n,parsed,None
        except Exception as exc:return n,None,str(exc)[:160]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        for n,parsed,error in ex.map(worker,MAXPREPS_6A.items()):
            if error:statuses[n]={'status':'unavailable','error':error,'url':MAXPREPS_6A[n]};continue
            found.extend(parsed['fixtures'])
            statuses[n]={'status':'read','fixtures':len(parsed['fixtures']),
                'unmapped':parsed['unmapped'],'outsideWindow':parsed['outsideWindow'],
                'lastUpdated':parsed['lastUpdated'],'ageDays':parsed['ageDays'],
                'stale':parsed['stale'],'url':MAXPREPS_6A[n]}
    missing_map={}; date_conflicts=[]
    for g in found:
        key=unique_fixture_key(g)
        if key in existing_keys:continue
        pair=tuple(sorted((g['home'],g['away'])))
        if pair in by_pair:
            orig=by_pair[pair]
            issue={'matchup':f'{g["away"]} @ {g["home"]}', 'reportedDate':g['date'],
                   'existingDate':orig['date'], 'url':g['url']}
            if issue not in date_conflicts:date_conflicts.append(issue)
            continue
        group=missing_map.setdefault(key,{'date':g['date'],'home':g['home'],'away':g['away'],
                                           'sourceTeams':[],'sourceURLs':[],'venueConflict':False})
        if g['home']!=group['home'] or g['away']!=group['away']:
            group['venueConflict']=True
        if g['sourceTeam'] not in group['sourceTeams']:
            group['sourceTeams'].append(g['sourceTeam']);group['sourceURLs'].append(g['url'])
    missing=[];confirmed=[]
    for obj in missing_map.values():
        obj['verification']='both-teams-maxpreps' if obj['home'] in obj['sourceTeams'] and obj['away'] in obj['sourceTeams'] else 'one-sided-maxpreps'
        missing.append(obj)
        if obj['verification']=='both-teams-maxpreps' and not obj['venueConflict']:
            confirmed.append({'date':obj['date'],'home':obj['home'],'away':obj['away'],
                              'played':False,'homeScore':None,'awayScore':None,
                              'scoreSource':'two-team MaxPreps schedule cross-check'})
    return {'checkedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'read':sum(x['status']=='read' for x in statuses.values()),
            'staleCount':sum(x.get('stale',False) for x in statuses.values()),
            'total':len(MAXPREPS_6A),'teams':statuses,
            'potentialMissing':sorted(missing,key=lambda g:(g['date'],g['home'])),
            'dateConflicts':date_conflicts,'confirmedAdditions':confirmed}

def periodic_maxpreps(http_get):
    if MP_CACHE.exists():
        try:
            age=time.time()-MP_CACHE.stat().st_mtime
            if age<MP_AUDIT_INTERVAL:
                return json.loads(MP_CACHE.read_text(encoding='utf-8'))
        except Exception:pass
    audit=schedule_audit(http_get)
    # Keep the previous checked snapshot on a total outage.
    if audit['read'] or not MP_CACHE.exists():
        temp=MP_CACHE.with_suffix('.tmp')
        temp.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(MP_CACHE)
        return audit
    try:
        old=json.loads(MP_CACHE.read_text(encoding='utf-8'))
        old['lastAttemptWarning']='The latest MaxPreps check was unavailable; showing previous schedule comparison.'
        return old
    except Exception:return audit


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; D1FootballTracker/2.0; local research refresh)','Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=12) as resp:
        if resp.status!=200:raise RuntimeError('HTTP '+str(resp.status))
        raw=resp.read(1500000)
        return raw.decode('utf-8','replace')

def unique_fixture_key(g):return (g['date'], tuple(sorted((g['home'],g['away']))))

def update_network(scores):
    """Combine district schedules without accepting contradictory final scores.

    School pages can differ by one day. The matchup is one game, not two.
    Conflicting scores cannot be verified; keep the fixture with no final rather
    than picking whichever school's page happened to be read first.
    """
    original=list(SEED['games'])
    grouped={}
    errors=[]
    def same_match(a,b):
        if {a['home'],a['away']}!={b['home'],b['away']}:return False
        try:
            return abs((dt.date.fromisoformat(a['date'])-dt.date.fromisoformat(b['date'])).days)<=2
        except (ValueError,KeyError):return False
    for g in scores:
        if not g.get('date') or not g.get('home') or not g.get('away'):continue
        key=next((k for k,x in grouped.items() if same_match(x[0],g)),None)
        if key is None:key=len(grouped);grouped[key]=[]
        grouped[key].append(g)
    out=[]
    for group in grouped.values():
        match=group[0]
        seed=next((x for x in original if same_match(x,match)),None)
        base=seed or match
        finals=set()
        for g in group:
            if not g.get('played') or g.get('homeScore') is None or g.get('awayScore') is None:continue
            scores_by_team=((g['home'],int(g['homeScore'])),(g['away'],int(g['awayScore'])))
            finals.add(tuple(sorted(scores_by_team)))
        if len(finals)>1:
            errors.append('Conflicting official final scores: '+match['away']+' @ '+match['home'])
            # A contradictory score must not become a verified final.
            out.append({**base,'id':base.get('id','live'+str(len(out)+1)),
                        'played':False,'homeScore':None,'awayScore':None,
                        'scoreConflict':True})
            continue
        if finals:
            observed=dict(next(iter(finals)))
            out.append({**base,'id':base.get('id','live'+str(len(out)+1)),
                        'homeScore':observed[base['home']],
                        'awayScore':observed[base['away']], 'played':True,
                        'scoreSource':SCHEDULE.format(slug(match['home']))})
        else:
            # An unavailable school page must never erase an already verified
            # final carried by the original October 15 district snapshot.
            if seed and seed.get('played'):
                out.append(dict(seed))
            else:
                out.append({**base,'id':base.get('id','live'+str(len(out)+1)),
                            'played':False,'homeScore':None,'awayScore':None,
                            'support':not (base['home'] in MAIN or base['away'] in MAIN)})
    return out,errors


def official_math_audit(rankings,latest_games,external):
    """Independently reconstruct points when *every* input is confirmed.

    Publication of total points and the quotient is authoritative for the
    standings; the district does not provide a separate official win/bonus
    subtotal. Never call a guessed opponent win record 'reconciled'.
    """
    all_games=[]
    for g in list(latest_games)+list(SEED['games']):
        if not ('2026-08-21'<=g.get('date','')<='2026-10-31'):continue
        if any({x['home'],x['away']}=={g['home'],g['away']} and
               abs((dt.date.fromisoformat(x['date'])-dt.date.fromisoformat(g['date'])).days)<=2
               for x in all_games):continue
        all_games.append(g)
    values={}
    classes=['6A','5A','4A','3A','2A','A']
    for name in sorted(MAIN):
        record=rankings[name]; expected_games=record['w']+record['l']
        scheduled=[g for g in all_games if name in (g['home'],g['away'])]
        completed=[g for g in scheduled if g.get('played') and
                   isinstance(g.get('homeScore'),int) and isinstance(g.get('awayScore'),int)]
        win_points=0;bonus_points=0;missing=[];verified_class=True
        official_opp_records=0;secondary_opp_records=0
        known_wins=0; known_losses=0
        for g in completed:
            other=g['away'] if g['home']==name else g['home']
            mine=g['homeScore'] if g['home']==name else g['awayScore']
            their=g['awayScore'] if g['home']==name else g['homeScore']
            if mine==their:
                missing.append(other+': tie requires review')
                continue
            if mine>their:
                known_wins+=1
                opponent=INDEX.get(other)
                category=opponent.get('cls') if opponent else None
                status=opponent.get('classStatus') if opponent else None
                if category in classes and status=='official-piaa':
                    win_points+=140-20*classes.index(category)
                else:
                    verified_class=False
                    missing.append(other+': official playing classification not independently verified')
            else:known_losses+=1
            if other in rankings:
                bonus_points+=10*rankings[other]['w'];official_opp_records+=1
            elif other in external:
                # May include out-of-window matches; display, do not certify.
                secondary_opp_records+=1
                missing.append(other+': outside-district win total is secondary/unverified')
            else:
                missing.append(other+': eligible opponent wins unknown')
        if len(completed)!=expected_games:
            missing.append(f'{len(completed)} final scores found; official record contains {expected_games} games')
        if known_wins!=record['w'] or known_losses!=record['l']:
            missing.append(f'W-L from verified scores {known_wins}-{known_losses} vs official {record["w"]}-{record["l"]}')
        divisor=expected_games or None
        rating=round(record['points']/divisor,3) if divisor else None
        # All completed games and opponents must have reliable data before
        # comparing the reconstructed sum with District 1 published points.
        complete=not missing and len(completed)==expected_games
        difference=record['points']-win_points-bonus_points if complete else None
        values[name]={
            'seed':record['seed'],'record':f'{record["w"]}-{record["l"]}',
            'officialPoints':record['points'], 'officialRating':rating,
            'calculatedWinPoints':win_points if complete else None,
            'calculatedBonusPoints':bonus_points if complete else None,
            'componentDifference':difference,
            'verifiedFinalScores':len(completed), 'gamesInOfficialRecord':expected_games,
            'verifiedDistrictOpponentRecords':official_opp_records,
            'secondaryOpponentRecords':secondary_opp_records,
            'status':('verified-match' if difference==0 else 'verified-discrepancy') if complete else 'incomplete',
            'issues':sorted(set(missing))}
    return {'officialRatingsVerified':sum(1 for x in values.values() if x['officialRating'] is not None),
            'componentMatches':sum(x['status']=='verified-match' for x in values.values()),
            'incomplete':sum(x['status']=='incomplete' for x in values.values()),
            'componentDiscrepancies':sum(x['status']=='verified-discrepancy' for x in values.values()),
            'teams':values,
            'note':'District 1 does not publish the win/bonus split; components are independently reconstructed only with verified games, class and eligible opponent wins.'}

def scrape_once(http_get=fetch,team_names=None,external_sources=None):
    standing=parse_rankings(http_get(STANDINGS))
    # Full District 1 opponent schedules are followed as well, even for teams below 6A.
    names=team_names or sorted(t['name'] for t in SEED['teams'] if t['name'].isupper())
    scores=[];warnings=[]
    def work(n):
        try:
            h=http_get(SCHEDULE.format(slug(n)))
            f=parse_schedule(h,n)
            if not f: return n,[],f'No schedule table found: {n}'
            return n,f,None
        except Exception as exc:return n,[],f'{n}: {type(exc).__name__}: {str(exc)[:100]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for n,results,err in ex.map(work,names):
            scores.extend(results)
            if err:warnings.append(err)
    matches,errors=update_network(scores)
    audit=periodic_maxpreps(http_get)
    # Only double-confirmed, previously unlisted games are eligible for a live
    # schedule addition. MaxPreps scores are NOT used to overwrite official scores.
    seen={unique_fixture_key(g) for g in SEED['games']} | {unique_fixture_key(g) for g in matches}
    for g in audit.get('confirmedAdditions',[]):
        if unique_fixture_key(g) not in seen:
            matches.append({**g,'id':'mp'+str(len(matches)+1),
                            'support':not (g['home'] in MAIN or g['away'] in MAIN)})
            seen.add(unique_fixture_key(g))
    external={}
    sources=EXTERNAL_SOURCES if external_sources is None else external_sources
    def get_external(item):
        name,url=item
        try:return name,parse_external_record(http_get(url),url),None
        except Exception as exc:return name,None,f'{name} (supplemental): {type(exc).__name__}: {str(exc)[:90]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for n,value,err in ex.map(get_external,sources.items()):
            if value:
                previous=INDEX.get(n,{})
                if previous.get('w') is not None and (value['w']+value['l']) < (previous['w']+previous.get('l',0)):
                    warnings.append(f'{n}: supplemental games lag baseline; not imported')
                    continue
                external[n]=value
                if value.get('warning'):warnings.append(f'{n}: {value["warning"]}')
            if err:warnings.append(err)
    if not any(g['home'] in MAIN or g['away'] in MAIN for g in matches):
        warnings.append('No 6A school schedules returned; rankings will still refresh')
    return {'checkedAt':dt.datetime.now(dt.timezone.utc).isoformat(), 'rankings':standing,'games':matches,'externalRecords':external,'mathAudit':official_math_audit(standing,matches,external),'warnings':warnings+errors, 'source':STANDINGS,'schoolSchedulesRead':len(names),'supplementalRecordsRead':len(external),'teamCount6A':len(MAIN),'maxprepsAudit':audit}

def store_live(feed):
    tmp=CACHE.with_suffix('.tmp');tmp.write_text(json.dumps(feed,indent=2,ensure_ascii=False),encoding='utf8');tmp.replace(CACHE)

def once():
    global active,last_error,last_attempt,cached
    with lock:
        if active:return False
        active=True;last_attempt=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        feed=scrape_once()
        store_live(feed)
        with lock: cached=feed;last_error=''
        print(f'[{last_attempt}] Synced {len(feed["rankings"])} D1 standings, {len(feed["games"])} games, {len(feed.get("externalRecords",{}))} supplemental opponent records; warnings={len(feed["warnings"])}',flush=True)
        return True
    except Exception as e:
        with lock:last_error=f'{type(e).__name__}: {e}'
        print('Refresh failed, retained last valid feed:',last_error,flush=True)
        return False
    finally:
        with lock:active=False

def refresh_if_due():
    """Schedule one update if needed, without blocking a site visitor.

    This also lets a free hosting service catch up after waking from sleep.
    """
    with lock:
        previous=last_attempt
        busy=active
    if busy:
        return False,'Already checking official scores'
    if previous:
        try:
            elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(previous)).total_seconds()
            if elapsed<REFRESH_INTERVAL:
                return False,'Last check was less than 15 minutes ago'
        except (ValueError,TypeError):
            pass
    threading.Thread(target=once,daemon=True,name='piaa-refresh').start()
    return True,'Official results check started'

def repeat():
    while True:
        refresh_if_due()
        time.sleep(30)  # visit-independent schedule while the server is awake

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/data':
            refresh_if_due()
            with lock:doc={'ok':bool(cached),'refreshing':active,'lastError':last_error,'lastAttempt':last_attempt,'feed':cached}
            return self.json(doc)
        if path=='/api/refresh':
            started,message=refresh_if_due()
            return self.json({'started':started,'message':message})
        if path=='/api/audit':
            with lock:doc={'ok':bool(cached),'checkedAt':cached.get('checkedAt') if cached else None,'mathAudit':cached.get('mathAudit',{}) if cached else {}}
            return self.json(doc)
        if path=='/health':
            with lock:doc={'status':'ok','refreshing':active,'lastSuccess':cached.get('checkedAt') if cached else None}
            return self.json(doc)
        if path in ('/','/index.html'):
            contents=(ROOT/'index.html').read_bytes();return self.send_bytes(contents,'text/html; charset=utf-8')
        if path=='/data/2026_rankings_and_games.json':
            return self.send_bytes((ROOT/'2026_rankings_and_games.json').read_bytes(),'application/json')
        self.send_error(404,'Not found')
    def json(self,obj):return self.send_bytes(json.dumps(obj).encode('utf8'),'application/json')
    def send_bytes(self,data,kind):
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',len(data));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def log_message(self,format,*args):pass

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')))
    a.add_argument('--host',default=os.environ.get('HOST','127.0.0.1'))
    a.add_argument('--no-browser',action='store_true')
    a.add_argument('--once',action='store_true')
    args=a.parse_args()
    if CACHE.exists():
        try:cached=json.loads(CACHE.read_text(encoding='utf-8'))
        except Exception:pass
    if args.once:once();raise SystemExit(0 if cached else 1)
    print(f'2026 District One 6A Tracker listening on {args.host}:{args.port}',flush=True)
    print('Official rankings update every 15 minutes when the server is running; everyone sees the same feed.',flush=True)
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    threading.Thread(target=repeat,daemon=True,name='piaa-scheduler').start()
    if not args.no_browser and args.host in ('127.0.0.1','localhost'):
        import webbrowser
        threading.Timer(1.0,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}/')).start()
    server.serve_forever()
