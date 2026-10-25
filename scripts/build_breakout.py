import json, urllib.parse, math
from pathlib import Path

SIM='https://simbad.cds.unistra.fr/simbad/sim-id?Ident='
RSG='https://arxiv.org/html/astro-ph/0504337v1'
WR='https://arxiv.org/html/1412.0699v2'
SH='https://arxiv.org/abs/1512.01529'
NML='https://arxiv.org/abs/2505.02643'
NML_D='https://www.aanda.org/articles/aa/full_html/2025/06/aa54748-25/aa54748-25.html'
HARPER='https://arxiv.org/abs/1706.06020'
DUPREE='https://arxiv.org/abs/2208.01676'
ANTWIND='https://arxiv.org/abs/2006.08023'
ANTOBS='https://doi.org/10.1051/0004-6361/201321063'
VX='https://arxiv.org/abs/2011.09184'
RHO='https://arxiv.org/abs/2408.02756'
V509='https://arxiv.org/abs/2406.08276'
GUZIK='https://arxiv.org/abs/2410.23985'
PCYG='https://arxiv.org/abs/astro-ph/9908309'

# Exact SIMBAD main IDs and J2000 ICRS sexagesimal coordinates read directly from opened SIMBAD records.
RSG_ROWS=[
('Betelgeuse','Betelgeuse','* alf Ori','05 55 10.30536 +07 24 25.4304','M2 I',0.222,0.62),
('Antares','Antares','* alf Sco','16 29 24.45970 -26 25 55.2094','M1.5Iab+B2Vn',None,None),
('mu Cep','mu Cep','* mu. Cep','21 43 30.4595558543 +58 46 48.165937434','M1 I',0.87,2.01),
('VY CMa','VY CMa','V* VY CMa','07 22 58.3261352189 -25 46 03.194390594','M5Iae',1.2,None),
('NML Cyg','NML Cyg','NML Cyg','20 46 25.5392819088 +40 06 59.464289232','M7/8',1.6,None),
('VX Sgr','VX Sgr','V* VX Sgr','18 08 04.0442790744 -22 13 26.600899044','M8.5Ia',None,None),
('S Per','S Per','V* S Per','02 22 51.7113133056 +58 35 11.422774248','M4.5 I',None,4.18),
('SU Per','SU Per','V* SU Per','02 22 06.8948309496 +56 36 14.893650072','M3–4 I',None,2.01),
('RS Per','RS Per','V* RS Per','02 22 24.2955658080 +57 06 34.102933812','M4 I',None,2.63),
('BI Cyg','BI Cyg','V* BI Cyg','20 21 21.8869298736 +36 55 55.728708060','M3–4 I',None,5.11),
('BC Cyg','BC Cyg','V* BC Cyg','20 21 38.5478957040 +37 31 58.925226936','M3 I',None,5.58),
('RW Cyg','RW Cyg','V* RW Cyg','20 28 50.5903286280 +39 58 54.425527932','M3 I',None,4.49),
('TV Gem','TV Gem','V* TV Gem','06 11 51.4142883048 +21 52 05.653085916','M1 I',None,2.17),
('KY Cyg','KY Cyg','V* KY Cyg','20 25 58.0435428576 +38 21 07.671813480','M3–4 I',None,7.75),
('KW Sgr','KW Sgr','V* KW Sgr','17 52 00.7269495408 -28 01 20.555654448','M1.5 I',None,4.65),
('BU Gem','HD 42543','* 6 Gem','06 12 19.0988355816 +22 54 30.653107164','M0 I',None,2.01),
('YZ Per','YZ Per','V* YZ Per','02 38 25.4198516592 +57 02 46.194337896','M2 I',None,2.32),
('psi1 Aur','psi01 Aur','* psi01 Aur','06 24 53.9015502096 +49 17 16.411221960','M0 I',None,0.62),
('sigma CMa','Sigma CMa','* sig CMa','07 01 43.1480404483 -27 56 05.389225598','M1.5 I',None,0.16),
('zeta Cep','Zeta Cephei','* zet Cep','22 10 51.2777055617 +58 12 04.542602641','K1.5 I',None,0.00),
('V424 Lac','V424 Lac','V* V424 Lac','22 56 25.9983901008 +49 44 00.758688324','M0 I',None,0.31)
]
WR_ROWS=[
('WR 11','* gam02 Vel','08 09 31.95013 -47 20 11.7108','WC8+O7.5III',0.34),
('WR 147','EM* AS 431','20 36 43.6322747712 +40 21 07.442607924','WN8(h)+OB',0.73),
('WR 94','HD 158860','17 33 07.0670597184 -33 38 23.495487072','WN5',0.78),
('WR 90','HD 156385','17 19 29.9012420376 -45 38 23.874269568','WC7',1.15),
('WR 136','HD 192163','20 12 06.5418877464 +38 21 17.784181008','WN6b(h)',1.3),
('WR 137','HD 192641','20 14 31.7666855880 +36 39 39.598210224','WC7+O9',1.3),
('WR 144','MR 110','20 32 03.0201049320 +41 15 20.499732216','WC4',1.40),
('WR 78','HD 151932','16 52 19.2477039480 -41 51 16.270066224','WN7',1.64),
('WR 6','HD 50896','06 54 13.0439608392 -23 55 42.023319852','WN4b',1.80),
('WR 111','HD 165763','18 08 28.4692108104 -21 15 11.183076540','WC5',1.9),
('WR 134','HD 191765','20 10 14.1928045152 +36 10 35.070683376','WN6b',1.9),
('WR 135','HD 192103','20 11 53.5274337792 +36 11 50.525765304','WC8',1.9),
]
OTHER_ROWS=[
('Rigel','Rigel','* bet Ori','05 14 32.27210 -08 12 05.8981','BSG','B8Ia'),
('Alnilam','Alnilam','* eps Ori','05 36 12.81335 -01 12 06.9089','BSG','B0Ia'),
('Saiph','Saiph','* kap Ori','05 47 45.3888404 -09 40 10.577707','BSG','B0.5Ia'),
('Deneb','Deneb','* alf Cyg','20 41 25.91514 +45 16 49.2197','BSG','A2Ia'),
('rho Cas','rho Cas','* rho Cas','23 54 23.0325302520 +57 29 57.774737400','YSG','G2 Ia0'),
('V509 Cas','V509 Cas','V* V509 Cas','23 00 05.1012218544 +56 56 43.350876312','YSG','G4 Ia0'),
('P Cyg','P Cyg','* P Cyg','20 17 47.2019733389 +38 01 58.549132671','LBV','B1-2Ia-0ep'),
]

ref_rsg='2005ApJ...628..973L'
ref_wr='2015MNRAS.447.2322R'
ref_sh='2016AJ....151...51S'
ref_harper='2017AJ....154...11H'
ref_nml='2025A&A...698A.179D'
ref_rho='2024ApJ...974..113A'
ref_vx='2021A&A...646A..98T'
ref_pcyg='1999SSRv...90..493I'

def equatorial(coord):
    h,mi,s,dd,dm,ds=coord.split()
    ra=15*(float(h)+float(mi)/60+float(s)/3600)
    sign=-1 if dd.startswith('-') else 1
    de=sign*(abs(float(dd))+float(dm)/60+float(ds)/3600)
    return round(ra,9),round(de,9)

def entry(q,id,co,typ,sp,dist,av,sp_url,dist_url=None,av_url=None,stage_url=None):
    url=SIM+urllib.parse.quote(q,safe='')
    ra,dec=equatorial(co)
    sources={'ra_deg':url,'dec_deg':url,'class':stage_url or url,'spectral_type':sp_url}
    if dist is not None: sources['distance_kpc']=dist_url
    if av is not None: sources['extinction_av_mag']=av_url
    uncertain=[]
    if dist is None: uncertain.append('distance_kpc')
    if av is None: uncertain.append('extinction_av_mag')
    return {
        'star_id':id,'ra_deg':ra,'dec_deg':dec,'class':typ,'spectral_type':sp,
        'distance_kpc':dist,'extinction_av_mag':av,
        'lit':{
            'mass_loss':{'value':None,'reason':'No object-specific mass-loss evidence verified in the opened sources.'},
            'variability':{'value':None,'reason':'No object-specific variability evidence verified in the opened sources.'},
            'evolved_stage':{'value':{'RSG':'red supergiant','WR':'Wolf-Rayet','BSG':'blue supergiant','YSG':'yellow hypergiant','LBV':'luminous blue variable'}[typ],
                             'reason':'The cited classification supports this evolved stellar class, not a predicted explosion time.'},
            'confidence':{'value':None,'reason':'No calibrated zero-to-one core-collapse confidence is published in the opened sources.'},
            'evidence':[]},
        'sources':sources,'uncertain':uncertain,'simulated':False
    }

def evidence(record,bib,claim,url):
    ix=len(record['lit']['evidence'])
    record['lit']['evidence'].append({'bibcode':bib,'claim':claim})
    record['sources'][f'lit.evidence[{ix}]']=url
    if bib is None:
        record['uncertain'].append(f'lit.evidence[{ix}].bibcode')

def field(record,key,val,reason,source=None):
    record['lit'][key]={'value':val,'reason':reason}
    if source: record['sources']['lit.'+key]=source

def done(record):
    for k in ('mass_loss','variability','evolved_stage','confidence'):
        if record['lit'][k]['value'] is None and 'lit.'+k not in record['uncertain']:
            record['uncertain'].append('lit.'+k)
    return record

out=[]

for nick,q,id,co,sp,dist,av in RSG_ROWS:
    s=entry(q,id,co,'RSG',sp,dist,av,RSG if av is not None else SIM+urllib.parse.quote(q,safe=''),
            HARPER if nick=='Betelgeuse' else SH if nick in ('mu Cep','VY CMa') else NML_D if nick=='NML Cyg' else None,
            RSG if av is not None else None,
            SIM+urllib.parse.quote(q,safe=''))
    # Older paper supplies the classification and visual extinction for fitted stars.
    if av is not None:
        evidence(s,ref_rsg,'Optical spectrophotometry establishes the revised red-supergiant subtype and model-fit visual extinction.',RSG)
    if nick=='Betelgeuse':
        evidence(s,ref_harper,'Astrometric modeling gives a nominal distance of 222 pc with substantial systematic uncertainty.',HARPER)
        evidence(s,None,'Photometric and spectroscopic evidence supports a surface mass ejection and changed pulsations after the Great Dimming.',DUPREE)
        field(s,'mass_loss','observed episodic ejection','The Great Dimming study attributes atmospheric changes to an observed surface mass ejection.',DUPREE)
        field(s,'variability','documented','Published time-series observations show historic dimming and changes in pulsations.',DUPREE)
    elif nick=='Antares':
        evidence(s,None,'Radio and millimeter spectral indices distinguish chromospheric and wind-dominated emission from Antares.',ANTWIND)
        field(s,'mass_loss','wind observed','ALMA and VLA measurements reveal a wind-dominated radio-emission component.',ANTWIND)
        field(s,'variability','catalogued variable','SIMBAD lists Antares among variable stars.',s['sources']['ra_deg'])
    elif nick in ('mu Cep','VY CMa'):
        evidence(s,ref_sh,'Infrared dust imaging models the object-specific circumstellar mass-loss history.',SH)
        field(s,'mass_loss','observed and modeled','SOFIA infrared observations and dust modeling establish circumstellar mass loss.',SH)
    elif nick=='NML Cyg':
        evidence(s,ref_nml,'NOEMA observations reveal a dense asymmetric circumstellar envelope consistent with strong mass loss.',NML)
        field(s,'mass_loss','observed and modeled','NOEMA dust and CO observations constrain an ongoing extended outflow.',NML)
    elif nick=='VX Sgr':
        evidence(s,ref_vx,'Spectroscopic analysis considers both red-supergiant and extreme AGB interpretations.',VX)
        field(s,'evolved_stage','disputed RSG / high-mass AGB','SIMBAD labels an RSG, but published spectroscopy favors an extreme AGB interpretation.',VX)
        s['uncertain'].extend(['class','lit.evolved_stage'])
    elif len(s['lit']['evidence'])==0:
        # For NML, Antares and VX the direct paper evidence is already attached. All others from Levesque sample.
        evidence(s,ref_rsg,'The object is included in the Galactic red-supergiant spectroscopic sample.',RSG)
    if nick.startswith('V') or nick in ('S Per','SU Per','RS Per','BI Cyg','BC Cyg','RW Cyg','TV Gem','KY Cyg','KW Sgr','YZ Per'):
        if id.startswith('V*'):
            field(s,'variability','catalogued variable','SIMBAD identifies the target with a variable-star main identifier.',s['sources']['ra_deg'])
    out.append(done(s))

for q,id,co,sp,dist in WR_ROWS:
    s=entry(q,id,co,'WR',sp,dist,None,WR,WR,None,WR)
    evidence(s,ref_wr,'The published nearby Wolf-Rayet sample lists this system, spectral classification and heliocentric distance.',WR)
    if q in ('WR 11','WR 137','WR 147'):
        s['uncertain'].append('binary_evolution_outcome')
        s['lit']['evolved_stage']['reason']='The system contains a Wolf-Rayet star and a published companion classification; later binary evolution is unresolved.'
    # Paper supports class-level winds but no star-specific mass-loss rate, hence leave mass_loss null.
    out.append(done(s))

for nick,q,id,co,typ,sp in OTHER_ROWS:
    objurl=SIM+urllib.parse.quote(q,safe='')
    stage_url={
        'Rigel':objurl,'Alnilam':objurl,'Saiph':objurl,'Deneb':GUZIK,
        'rho Cas':RHO,'V509 Cas':V509,'P Cyg':PCYG
    }[nick]
    s=entry(q,id,co,typ,sp,None,None,objurl,None,None,stage_url)
    if nick in ('Rigel','Alnilam','Saiph'):
        evidence(s,None,'The study examines the star light curves but reports insufficient coverage for firm variability comparisons.',GUZIK)
        field(s,'variability',None,'The published light curves are too sparse for a firm object-specific variability conclusion.',GUZIK)
    elif nick=='Deneb':
        evidence(s,None,'Time-series photometry documents irregular alpha-Cygni-type brightness variability.',GUZIK)
        field(s,'variability','documented','Published long-baseline photometry shows irregular pulsations in Deneb.',GUZIK)
    elif nick=='rho Cas':
        evidence(s,ref_rho,'CHARA observations reveal prominent convection cells and a circumstellar envelope in the yellow hypergiant.',RHO)
        evidence(s,ref_sh,'Infrared emission is consistent with dust shell material from a documented past eruption.',SH)
        field(s,'mass_loss','historical ejection documented','Infrared observations trace the expanding dust shell of a past eruption.',SH)
        field(s,'variability','eruptive variability documented','The yellow-hypergiant observations describe recurrent dimming and recovery episodes.',RHO)
    elif nick=='V509 Cas':
        evidence(s,None,'Spectroscopic and photometric monitoring identifies V509 Cas as a yellow hypergiant with earlier mass-loss outbursts.',V509)
        field(s,'mass_loss','historical eruptive loss documented','The yellow-hypergiant study reports historical eruptive mass-loss outbursts.',V509)
        field(s,'variability','low-amplitude monitoring variability','Multi-year photometric and spectroscopic monitoring shows small present-day variations.',V509)
    elif nick=='P Cyg':
        evidence(s,ref_pcyg,'Review documents eruptions, variable winds and luminous-blue-variable behavior.',PCYG)
        field(s,'mass_loss','winds and past eruptions documented','Review describes strong winds and historical eruptive mass loss.',PCYG)
        field(s,'variability','historical photometric eruptions','The observational review records eruptive photometric history.',PCYG)
    out.append(done(s))

assert len(out)==40,len(out)
assert len(set(x['star_id'] for x in out))==40
for x in out:
    assert 0 <= x['ra_deg'] < 360 and -90<=x['dec_deg']<=90
    for f in ['ra_deg','dec_deg']:
        assert f in x['sources']
    for f in ['distance_kpc','extinction_av_mag']:
        assert (x[f] is not None)==(f in x['sources'])
    assert x['lit']['confidence']['value'] is None
    assert 'lit.confidence' in x['uncertain']
    assert x['simulated'] is False
    for k,e in enumerate(x['lit']['evidence']):
        assert f'lit.evidence[{k}]' in x['sources']

path=Path('/mnt/data/data/stars/curated_stars.json')
path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'path':str(path),'count':len(out),'distance_verified':sum(x['distance_kpc'] is not None for x in out),'av_verified':sum(x['extinction_av_mag'] is not None for x in out),'json_bytes':path.stat().st_size,'counts':{cl:sum(x['class']==cl for x in out) for cl in ['RSG','WR','BSG','YSG','LBV']}},indent=2))
