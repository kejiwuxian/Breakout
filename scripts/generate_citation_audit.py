import json, re
from pathlib import Path
path=Path('/mnt/data/data/stars/curated_stars.json')
stars=json.loads(path.read_text())
assert len(stars)==40
aliases={
'* alf Ori':'Betelgeuse (α Ori)','* alf Sco':'Antares (α Sco)','* mu. Cep':'μ Cep','V* VY CMa':'VY CMa','NML Cyg':'NML Cyg','V* VX Sgr':'VX Sgr','V* S Per':'S Per','V* SU Per':'SU Per','V* RS Per':'RS Per','V* BI Cyg':'BI Cyg','V* BC Cyg':'BC Cyg','V* RW Cyg':'RW Cyg','V* TV Gem':'TV Gem','V* KY Cyg':'KY Cyg','V* KW Sgr':'KW Sgr','* 6 Gem':'BU Gem (6 Gem)','V* YZ Per':'YZ Per','* psi01 Aur':'ψ¹ Aur','* sig CMa':'σ CMa','* zet Cep':'ζ Cep','V* V424 Lac':'V424 Lac','* gam02 Vel':'WR 11 (γ² Vel)','EM* AS 431':'WR 147','HD 158860':'WR 94','HD 156385':'WR 90','HD 192163':'WR 136','HD 192641':'WR 137','MR 110':'WR 144','HD 151932':'WR 78','HD 50896':'WR 6','HD 165763':'WR 111','HD 191765':'WR 134','HD 192103':'WR 135','* bet Ori':'Rigel','* eps Ori':'Alnilam','* kap Ori':'Saiph','* alf Cyg':'Deneb','* rho Cas':'ρ Cas','V* V509 Cas':'V509 Cas','* P Cyg':'P Cygni'}
assert len(aliases)==40
rows=[]
for s in stars:
 for i,e in enumerate(s['lit']['evidence']):
  url=s.get('sources',{}).get(f'lit.evidence[{i}]')
  bibcode=e.get('bibcode')
  category=s['class']
  if bibcode=='2005ApJ...628..973L':
   status='partly'
   fix='Keep paper; cite Tables 1 & 4. Abstract reports cohort results, not this star’s subtype or A_V.'
  elif bibcode=='2015MNRAS.447.2322R':
   status='partly'
   fix='Keep paper; cite Appendix D, Table D1. Abstract does not report this system’s distance/type.'
  elif s['star_id']=='* alf Sco' and bibcode=='2013A&A...555A..24O':
   status='yes'; fix='Replace inaccessible publisher DOI with opened arXiv:1304.4800; keep verified bibcode.'
  elif s['star_id']=='* P Cyg':
   status='partly'; fix='Narrow claim to historic eruptions, unusual stellar wind, and LBV-like properties; abstract does not explicitly establish wind variability.'
  elif s['star_id']=='V* VX Sgr':
   status='yes'; fix='Keep; flag that authors favor an extreme AGB interpretation, not RSG confirmation.'
  elif bibcode is None:
   status='yes'; arxiv=re.search(r'(\d{4}\.\d{4,5}|astro-ph/\d{7})',url or '')
   fix=('Keep claim. Store arXiv:'+arxiv.group(1)+' as the citation identifier; bibcode currently null.') if arxiv else 'Retain link; bibliographic identifier unverified.'
  elif bibcode=='2017AJ....154...11H':
   status='yes'; fix='Keep nominal 222 pc estimate with its +48/-34 pc uncertainty; do not present as exact.'
  else: status='yes'; fix='Keep; abstract directly supports the stated claim.'
  access='no' if s['star_id']=='* alf Sco' and bibcode=='2013A&A...555A..24O' else 'yes'
  rows.append({'star':aliases[s['star_id']],'star_id':s['star_id'],'bibcode':bibcode,'arxiv_id':re.search(r'(\d{4}\.\d{4,5}|astro-ph/\d{7})',url or '').group(1) if re.search(r'(\d{4}\.\d{4,5}|astro-ph/\d{7})',url or '') else None,'url':url,'link_opens':access,'on_topic':'yes','claim_supported':status,'claim':e['claim'],'fix':fix,'simulated':False})
assert len(rows)==45
from collections import Counter
print(Counter(x['claim_supported'] for x in rows),Counter(x['link_opens'] for x in rows))
Out=Path('/mnt/data/data/stars')
(Out/'citation_audit.json').write_text(json.dumps({'review_date':'2026-10-24','scope':'literature evidence links only','simulated':False,'rows':rows},ensure_ascii=False,indent=2)+'\n')
lines=['# BREAKOUT curated_stars.json citation audit','', 'Audit basis: directly opened arXiv abstract pages and HTML full text where needed. The Antares publisher DOI redirected to a blocked publisher page; replacement arXiv:1304.4800 opened.','', '| Star | Bibcode / arXiv | Link opens? | On topic? | Claim supported by abstract? | Fix |','|---|---|---|---|---|---|']
for r in rows:
 cid=r['bibcode'] or ('arXiv:'+r['arxiv_id'] if r['arxiv_id'] else 'unverified')
 lines.append(f"| {r['star']} | [{cid}]({r['url']}) | {r['link_opens']} | {r['on_topic']} | {r['claim_supported']} | {r['fix']} |")
lines.extend(['', 'The original curated_stars.json was not modified.','', 'No synthetic measurements or simulated figures were used.'])
(Out/'citation_audit.md').write_text('\n'.join(lines)+'\n')
print('written',len(rows))
