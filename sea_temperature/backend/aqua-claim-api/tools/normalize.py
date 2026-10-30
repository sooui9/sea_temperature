import json, re, csv, sys
S=sys.argv[1]
def load(fn):
    it=json.load(open(f"{S}/{fn}.json")); secs=[]; cur=None
    for x in it:
        if x['type']=='p' and '적용가격 공시' in x['t']:
            cur={'title':x['t'],'items':[]}; secs.append(cur); continue
        if cur is None: continue
        if x['type']=='table':
            g=[['']*x['cols'] for _ in range(x['rows'])]
            for c in x['cells']:
                if c['r']<x['rows'] and c['c']<x['cols']: g[c['r']][c['c']]=' '.join(c['t'])
            cur['items'].append(('T',g))
        else: cur['items'].append(('P',x['t']))
    return secs
def num(s):
    s=s.replace(',','').strip(); return float(s) if re.fullmatch(r'[0-9.]+',s) else None
def weight_g(s):
    s=s.replace(',','').replace(' ',''); m=re.match(r'([0-9.]+)(kg|g)이상',s)
    if not m: return None
    v=float(m.group(1)); return v*1000 if m.group(2)=='kg' else v
def regions(label):
    l=label.replace(' ','')
    if l in ('모든권역','모든지역',''): return [None]
    l=l.replace('제','').replace('권역','').replace('∼','~')
    out=[]
    for part in l.split(','):
        if '~' in part: a,b=part.split('~'); out+=list(range(int(a),int(b)+1))
        elif part.isdigit(): out.append(int(part))
        else: return None
    return out
def period(sec):
    for k,t in sec['items']:
        if k=='P' and '적용기간' in t:
            m=re.findall(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',t)
            if len(m)==2: return tuple('%s-%02d-%02d'%(y,int(mo),int(d)) for y,mo,d in m)
    return (None,None)
def tables(sec): return [g for k,g in sec['items'] if k=='T' and not (len(g)==1 and len(g[0])==1)]

rows=[]; formulas=[]
def add(sec_name,notice,vf,vt,product_ids,species_ids,price,unit,region_label,scheme='해수면',variant=None,weight=None,month=None,size=None,note=None,src=None):
    rs=regions(region_label) if scheme in ('해수면','미확인') or region_label in ('모든권역','모든지역','') else None
    if rs is None: rs=['RAW']
    for pid in product_ids:
        for sid in species_ids:
            for r in rs:
                rows.append(dict(notice_month=notice,section=sec_name,product_id=pid,species_id=sid,variant=variant,
                  region_scheme=scheme if region_label not in ('모든권역','모든지역','') else 'ALL',
                  region_no=('' if r in (None,'RAW') else r),region_label=region_label or '모든권역',
                  weight_min_g=weight,size_label=size,month=month,price=price,unit=unit,valid_from=vf,valid_to=vt,note=note,source=src))
def weight_table(g,sec_name,notice,vf,vt,pids,sids,unit,scheme='해수면',src=None):
    # header row: first row containing a 권역/region label
    hi=next(i for i,r in enumerate(g) if r[0].replace(' ','') in ('체중','구분'))
    hdr=g[hi]; groups=[]; wc=None
    for j,h in enumerate(hdr):
        if h.replace(' ','') in ('체중','구분'): wc=j
        elif h: groups.append((wc,j,h))
    for r in g[hi+1:]:
        for wc,pc,lab in groups:
            w=weight_g(r[wc]) if r[wc] else None; p=num(r[pc]) if r[pc] else None
            if w is not None and p is not None: add(sec_name,notice,vf,vt,pids,sids,p,unit,lab,scheme,weight=w,src=src)

def month_of(s):
    m=re.match(r'(\d{1,2})월',s.strip()); return int(m.group(1)) if m else None

def process(fn,notice,srcname):
    for sec in load(fn):
        name=sec['title'].split(' 양식')[0].strip(); vf,vt=period(sec); T=tables(sec); src=f"{srcname} / {name}"
        def wt(g,p,s,u,scheme='해수면',sub=None): weight_table(g,name+(f'/{sub}' if sub else ''),notice,vf,vt,p,s,u,scheme,src)
        if name=='넙치': wt(T[0],[1],[1],'KRW_PER_KG')
        elif name=='전복': wt(T[0],[2],[22],'KRW_PER_KG')
        elif name=='육상수조식전복': wt(T[0],[18],[8],'KRW_PER_KG')
        elif name=='강도다리': wt(T[0],[11],[2],'KRW_PER_KG')
        elif name=='터봇': wt(T[0],[21],[4],'KRW_PER_KG')
        elif name=='해상가두리어류':
            subs=[t for k,t in sec['items'] if k=='P' and t.startswith('□')]
            mp={'조피볼락':([3],[11]),'쥐치(참쥐치 공통적용)':([3],[17,18]),'참돔':([3],[13]),'돌돔(육상수조식 돌돔 포함)':None,
                '감성돔':([3],[15]),'농어':([3],[16]),'볼락':([3],[12]),'가숭어':([3],[19]),'능성어':([3],[20])}
            for sub,g in zip(subs,T):
                s=sub.lstrip('□ ').strip()
                if s.startswith('돌돔'):
                    wt(g,[3],[14],'KRW_PER_FISH',sub='돌돔'); wt(g,[15],[3],'KRW_PER_FISH',sub='돌돔(육상수조식 준용)')
                else: wt(g,*mp[s],'KRW_PER_FISH',sub=s)
        elif name=='뱀장어':
            wt(T[0],[10],[6],'KRW_PER_FISH','미확인',sub='뱀장어'); wt(T[1],[10],[7],'KRW_PER_FISH','미확인',sub='이종뱀장어')
        elif name=='송어': wt(T[0],[14],[5],'KRW_PER_FISH','내수면')
        elif name=='메기': wt(T[0],[22],[23],'KRW_PER_FISH','내수면')
        elif name=='향어': wt(T[0],[23],[24],'KRW_PER_FISH','내수면')
        elif name=='다시마':
            g=T[0]
            for j in range(1,len(g[1])): add(name,notice,vf,vt,[13],[38],num(g[2][j]),'KRW_PER_KG',g[1][j],variant='식용_수확기',month=6,src=src)
            g=T[1]
            for j in range(1,13): add(name,notice,vf,vt,[13],[38],num(g[1][j]),'KRW_PER_KG','모든권역',variant='먹이용',month=month_of(g[0][j]),src=src)
            formulas.append(dict(section=name,product_id=13,variant='식용_비수확기',applies='본 양성 설치일 ~ 5월 31일',formula='수확기 적용가격(권역별) × (1 - 잔여일수 × 10% / 30)',base_price=None,period_end='05-31',floor=None,region_label='권역별(6월 수확기 가격 = applied_price 다시마 식용_수확기 행)',valid_from=vf,valid_to=vt,source=src))
        elif name=='멍게':
            g=T[0]
            for j in range(1,len(g[0])): add(name,notice,vf,vt,[8],[34],num(g[1][j]),'KRW_PER_KG','모든권역',variant='수확기',month=month_of(g[0][j]),src=src)
            formulas.append(dict(section=name,product_id=8,variant='비수확기',applies='본 양성 1차 이설 이후 ~ 동년 12월 31일',formula='3,105 × (1 - 잔여일수 × 10% / 30)',base_price=3105,period_end='12-31',floor=None,region_label='모든권역',valid_from=vf,valid_to=vt,source=src))
        elif name=='굴':
            g=T[0]
            for r in g[2:]: add(name,notice,vf,vt,[6],[29],num(r[1]),'KRW_PER_LINE','모든권역',variant='양성기간(수하 후 60일 미만)',size=r[0],src=src)
            g=T[1]
            for r in g[2:]:
                for j in (2,3): add(name,notice,vf,vt,[6],[29],num(r[j]),'KRW_PER_KG',g[1][j],variant='상품화기간(수하 후 60일 이상)',month=month_of(r[1]),note='알굴 중량 기준',src=src)
        elif name=='가리비':
            g=T[0]
            for r in g[2:]:
                for j in (2,3,4): add(name,notice,vf,vt,[16],[31,32,33],num(r[j]),'KRW_PER_KG',g[1][j],month=month_of(r[1]),src=src)
            formulas.append(dict(section=name,product_id=16,variant='생산비보장특약_국내산',applies='1ha 기준',formula='5,400,000 + 828,210 + 종패미수 × 6',base_price=6228210,period_end=None,floor=None,region_label='모든권역',valid_from=vf,valid_to=vt,source=src))
            formulas.append(dict(section=name,product_id=16,variant='생산비보장특약_중국산',applies='1ha 기준',formula='5,400,000 + 828,210 + 종패미수 × 4',base_price=6228210,period_end=None,floor=None,region_label='모든권역',valid_from=vf,valid_to=vt,source=src))
        elif name in ('홍합','오만둥이'):
            g=T[0]; pid,sid={'홍합':(12,30),'오만둥이':(20,36)}[name]
            for j in range(1,13): add(name,notice,vf,vt,[pid],[sid],num(g[2][j]),'KRW_PER_KG','모든권역',month=month_of(g[1][j]),src=src)
        elif name=='미역':
            g=T[0]; months=g[2]; var={1:'조기산',2:'만기산',3:'만기산',4:'만기산',11:'조기산',12:'조기산'}
            for r in g[3:6]:
                for j in range(1,9):
                    p=num(r[j]) if r[j] else None; m=month_of(months[j])
                    if p is not None: add(name,notice,vf,vt,[9],[37],p,'KRW_PER_KG',r[0],variant='수확기_'+var[m],month=m,src=src)
            for r in T[1][2:]:
                formulas.append(dict(section=name,product_id=9,variant='비수확기',applies='본 양성시설 설치 이후 ~ 동년 10월 31일',formula=f'{r[1]} × (1 - 잔여일수 × 10% / 30), 종묘가격 최저한도',base_price=num(r[1]),period_end='10-31',floor='종묘가격(금액 미공시)',region_label=r[0],valid_from=vf,valid_to=vt,source=src))
        elif name=='미더덕':
            g=T[0]
            for j in range(1,len(g[0])): add(name,notice,vf,vt,[19],[35],num(g[1][j]),'KRW_PER_KG','모든권역',variant='수확기',month=month_of(g[0][j]),src=src)
            formulas.append(dict(section=name,product_id=19,variant='비수확기',applies='7월 1일 ~ 익년 1월 31일',formula='12,307 × (1 - 잔여일수 × 10% / 30), 종묘가격 최저한도',base_price=12307,period_end='01-31',floor='종묘가격(금액 미공시)',region_label='모든권역',valid_from=vf,valid_to=vt,source=src))
        elif name=='전복종자':
            g=T[0]; mlab=[];cur=None
            for j in range(1,13):
                if g[1][j]: cur=month_of(g[1][j])
                add(name,notice,vf,vt,[24],[10],num(g[3][j]),'KRW_PER_FISH',g[2][j],scheme='군',variant='출하기',month=cur,src=src)
            for lab,b in (('완도',239),('진도,해남',232)):
                formulas.append(dict(section=name,product_id=24,variant='비출하기(1차선별 이후)',applies='5월 1일 ~ 10월 31일',formula=f'{b} × (사고시 크기mm / 21mm) × (1,000미 / 사고시 크기별 보상한도: 11mm미만 1,500미, 11~17mm 1,200미, 17mm이상 1,000미)',base_price=b,period_end='10-31',floor=None,region_label=lab,valid_from=vf,valid_to=vt,source=src))
        elif name.startswith('김(황백화'):
            g=T[0]; hdr=g[1]; reg=None
            for r in g[2:]:
                if r[0]: reg=r[0]
                lab=reg if not r[1] else f'{reg}/{r[1]}'
                for j in range(2,7):
                    ms=[10,11,12] if '10월~12월' in hdr[j] else [month_of(hdr[j])]
                    for m in ms:
                        if r[1]: add(name,notice,vf,vt,[4,5],[40,41],num(r[j]),'KRW_PER_KG',reg,variant=None,month=m,note=f'5권역 {r[1]}군 가격',src=src)
                        else: add(name,notice,vf,vt,[4,5],[40,41],num(r[j]),'KRW_PER_KG',reg,month=m,src=src)
        elif name=='해조류':
            g=T[0]; add(name,notice,vf,vt,[32],[40,41],num(g[2][1]),'KRW_PER_BOOK',g[1][1],variant='가이식 김(C003 특약)',src=src)
        elif name=='방어':
            g=T[0]
            for r in g[2:]: add(name,notice,vf,vt,[26],[26],num(r[1]),'KRW_PER_KG','모든권역',month=month_of(r[0]),src=src)
        elif name=='흰다리새우':
            g=T[0]
            add(name,notice,vf,vt,[25],[27],num(g[2][4])*1000,'KRW_PER_HA','모든권역',variant='평균생산비(2023~2025)',src=src)
            add(name,notice,vf,vt,[25],[27],num(g[2][5])*1000,'KRW_PER_HA','모든권역',variant='보장생산비용(평균의 80%)',src=src)
        elif name=='왕우렁이':
            specs=[('식용(단기형·장기형 1차입식)',T[0],2783,'08-31','2026-04-01~2026-08-31'),('식용(장기형 2차입식)',T[1],2852,'02-28(윤년 29)','2026-10-01~2027-02-28'),('비식용',T[2],9000,'04-30','2026-09-01~2027-04-30')]
            for v,g,b,end,ap in specs:
                for j in range(1,len(g[0])): add(name,notice,vf,vt,[27],[28],num(g[1][j]),'KRW_PER_KG','모든권역',variant=v+'_출하기',month=month_of(g[0][j]),note=('원문 출하기 표기 "2027.03.01 ~ 2026.03.31" 연도 오기' if '2차' in v else None),src=src)
                formulas.append(dict(section=name,product_id=27,variant=v+'_비출하기',applies=ap,formula=f'{b:,} × (1 - 잔여일수 × 10% / 30)',base_price=b,period_end=end,floor=None,region_label='모든권역',valid_from=vf,valid_to=vt,source=src))
        elif name=='미꾸라지':
            g=T[0]
            for j in range(1,len(g[0])): add(name,notice,vf,vt,[28],[25],num(g[1][j]),'KRW_PER_KG','모든권역',variant='동면기 이전',month=month_of(g[0][j]),note='동면기 이후(2027.05~07) 추후 공시',src=src)
        else: print('UNHANDLED',name)
process('oct','2026-10','붙임1_2026년10월')
process('sep','2026-09','붙임3_2026년09월')
# fill missing validity for 왕우렁이 (no 적용기간 line)
for r in rows:
    if r['valid_from'] is None and r['section']=='왕우렁이': r['note']=((r['note']+'; ') if r['note'] else '')+'원문에 적용기간 없음'
cols=list(rows[0].keys())
with open(f"{S}/out/applied_price_all.csv",'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,cols); w.writeheader(); w.writerows(rows)
with open(f"{S}/out/applied_price_formula.csv",'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,list(formulas[0].keys())); w.writeheader(); w.writerows(formulas)
sub=[r for r in rows if r['region_scheme']=='ALL' or (r['region_scheme']=='해수면' and r['region_no'] in (7,8))]
for r in sub: r['region_no']=r['region_no'] if r['region_no']!='' else '전권역'
with open(f"{S}/out/applied_price_r7_r8.csv",'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,cols); w.writeheader(); w.writerows(sub)
print(len(rows),len(formulas),len(sub))
