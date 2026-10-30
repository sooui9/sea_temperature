import olefile, zlib, struct, sys, json
def text(p):
    t=[];j=0
    while j<len(p):
        c=struct.unpack('<H',p[j:j+2])[0]
        if c in (1,2,3,4,5,6,7,8,9,11,12,14,15,16,17,18,19,20,21,22,23): j+=16; continue
        if c<32: t.append(' '); j+=2; continue
        t.append(chr(c)); j+=2
    return ' '.join(''.join(t).split())
f=olefile.OleFileIO(sys.argv[1]); comp=f.openstream('FileHeader').read()[36]&1
items=[]   # flat: paragraphs outside 'leaf' tables, and tables
stack=[]   # open cells: dict(lvl, remaining, cell, table)
pending_table=None
for s in sorted([x for x in f.listdir() if x[0]=='BodyText']):
    d=f.openstream(s).read()
    if comp: d=zlib.decompress(d,-15)
    i=0
    while i<len(d):
        h=struct.unpack('<I',d[i:i+4])[0]; i+=4
        tag=h&0x3ff; lvl=(h>>10)&0x3ff; sz=h>>20
        if sz==0xfff: sz=struct.unpack('<I',d[i:i+4])[0]; i+=4
        p=d[i:i+sz]; i+=sz
        if tag==66:
            # pop cells whose paragraphs are exhausted / that are at deeper level
            while stack and lvl<stack[-1]['lvl']: stack.pop()
            if stack and lvl==stack[-1]['lvl']:
                stack[-1]['remaining']-=1
                if stack[-1]['remaining']<0: stack.pop()
                while stack and lvl<stack[-1]['lvl']: stack.pop()
        elif tag==77:
            r,c=struct.unpack('<HH',p[4:8]); pending_table={'type':'table','rows':r,'cols':c,'cells':[]}; items.append(pending_table)
        elif tag==72 and len(p)>=16 and pending_table is not None:
            n=struct.unpack('<h',p[0:2])[0]; c,r,cs,rs=struct.unpack('<HHHH',p[8:16])
            while stack and lvl<=stack[-1]['lvl'] and stack[-1]['table'] is not pending_table: stack.pop()
            if stack and stack[-1]['table'] is pending_table and stack[-1]['lvl']==lvl: stack.pop()
            cell={'r':r,'c':c,'rs':rs,'cs':cs,'t':[]}; pending_table['cells'].append(cell)
            stack.append({'lvl':lvl,'remaining':n,'cell':cell,'table':pending_table})
        elif tag==67:
            t=text(p)
            if not t: continue
            if stack: stack[-1]['cell']['t'].append(t)
            else: items.append({'type':'p','t':t})
        if tag==72 and len(p)<16: pass
json.dump(items,open(sys.argv[2],'w'),ensure_ascii=False)
