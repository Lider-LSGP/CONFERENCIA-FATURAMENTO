"""Motor local, conservador e auditável. Nenhum dado é enviado a APIs externas."""
from __future__ import annotations
import hashlib, io, re, unicodedata, zipfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Callable
import pymupdf as fitz
from PIL import Image, ImageOps
import pytesseract
from rapidfuzz import fuzz

BENEFITS = ['VT GVBUS', 'VT Alvorada', 'VA', 'Saúde', 'Odonto', 'Seguro de vida', 'Idesbre', 'Sindicato', 'Ponto']
CPF_RE = re.compile(r'(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)')
MONEY = r'-?\d[\d.]*,\d{2}'

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s.upper())).strip()

def cpf_normalize(s):
    v = re.sub(r'\D', '', str(s))
    return v.zfill(11) if 1 <= len(v) <= 11 else ''

def cpf_valid(v):
    if len(v) != 11 or len(set(v)) == 1 or not v.isdigit(): return False
    for n in (9, 10):
        d = (sum(int(v[i]) * (n+1-i) for i in range(n)) * 10) % 11
        if (0 if d == 10 else d) != int(v[n]): return False
    return True

def uid(*items): return hashlib.sha256('|'.join(map(str, items)).encode()).hexdigest()[:20]

def discount_lines(block,label):
    found=[]
    for line in block.splitlines():
        match=re.search(label,line,re.I)
        if not match: continue
        # A folha tem proventos à esquerda e descontos à direita. Usa o tipo
        # do primeiro evento após a descrição, não qualquer D na linha inteira.
        event=re.search(r'('+MONEY+r')\s+('+MONEY+r')\s+([PD])\b',line[match.end():])
        if event and event.group(3)=='D':found.append(line)
    return found

def plausible_name(s):
    n = norm(s); t = n.split()
    if not (2 <= len(t) <= 12) or len(n) < 6: return False
    blocked = {'TOTAL','EMPRESA','CNPJ','BENEFICIARIO','BENEFICIARIOS','NOME','VALOR','SALDO','TITULAR','MATRICULA','CARTAO','COMPETENCIA','RELATORIO','PAGAMENTO','SACADO','COMPROVANTE','BANCO','CONTRATO','UNIMED','DEMONSTRATIVO','SEGURADO','SEGURADOS','SISTEMA','EMISSAO','RUBRICA','MOVIMENTOS','MENSALIDADE','PLANO','ASSISTENCIAL','COMERCIAL','PERCENTUAL','TRANSPORTE','PAGADOR','ENDERECO','COOPERATIVA','HOSPITAL','CONTROLE','COLABORADOR','ASSINATURA','FREQUENCIA'}
    return not bool(set(t) & blocked) and len(t[0]) >= 2

@dataclass
class Page:
    file: str
    file_hash: str
    number: int
    text: str
    lines: list[str]
    ocr: bool = False
    confidence: float = 100
    error: str = ''
    layout: str = ''
    records: int = 0
    competence: str = ''

@dataclass
class Person:
    id: str
    name: str
    cpf: str
    registration: str
    company: str
    cnpj: str
    contract: str
    competence: str
    job: str
    vt: bool
    union: bool
    file: str
    page: int
    evidence: str
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

@dataclass
class Record:
    id: str
    benefit: str
    name: str
    cpf: str
    file: str
    page: int
    evidence: str
    ocr: bool = False
    confidence: float = 100
    active: bool = True
    competence: str = ''
    amount: float | None = None
    registration: str = ''
    company_cnpj: str = ''
    warnings: list[str] = field(default_factory=list)


def unpack_files(files, max_total=180*1024*1024):
    """ZIP lido em memória: sem extração em disco, links, zip-slip ou ZIP recursivo."""
    out=[]; seen=set(); total=0; messages=[]
    for name,data in files:
        entries=[]
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if len(z.infolist()) > 250: raise ValueError('ZIP excede 250 entradas.')
                if sum(x.file_size for x in z.infolist()) > max_total: raise ValueError('ZIP excede o limite descompactado de 180 MB.')
                for info in z.infolist():
                    if info.is_dir() or not info.filename.lower().endswith('.pdf'): continue
                    if info.file_size > 60*1024*1024 or info.file_size / max(info.compress_size,1) > 150: raise ValueError('Entrada ZIP muito grande ou taxa de compressão suspeita.')
                    entries.append((name+' / '+info.filename.replace('\\','/').split('/')[-1],z.read(info)))
        elif name.lower().endswith('.pdf'): entries=[(name,data)]
        else: messages.append(f'{name}: formato ignorado (use PDF/ZIP).')
        for label,blob in entries:
            h=hashlib.sha256(blob).hexdigest()
            if h in seen: messages.append(f'{label}: arquivo idêntico ignorado.'); continue
            total+=len(blob)
            if total>max_total: raise ValueError('Lote excede 180 MB após descompactar.')
            if not blob.startswith(b'%PDF'): raise ValueError(f'{label}: assinatura PDF inválida.')
            seen.add(h); out.append((label,blob,h))
    return out,messages


def spatial_lines(p):
    words=p.get_text('words')
    if p.rotation:
        transformed=[]
        for w in words:
            box=fitz.Rect(w[:4])*p.rotation_matrix
            transformed.append((box.x0,box.y0,box.x1,box.y1,*w[4:]))
        words=transformed
    buckets=[]
    for w in sorted(words,key=lambda w:((w[1]+w[3])/2,w[0])):
        y=(w[1]+w[3])/2
        tolerance=max(1.7,min(3.8,(w[3]-w[1])*.35))
        if buckets and abs(buckets[-1][0]-y)<=tolerance: buckets[-1][1].append(w)
        else: buckets.append([y,[w]])
    return [' '.join(w[4] for w in sorted(row,key=lambda w:w[0])) for _,row in buckets]


def extract_pdf(name,data,h,ocr=True,dpi=180,progress:Callable|None=None,focus=''):
    pages=[]
    with fitz.open(stream=data,filetype='pdf') as d:
        if d.needs_pass: raise ValueError(f'{name}: PDF protegido por senha.')
        if len(d)>600: raise ValueError(f'{name}: PDF excede 600 páginas; divida o arquivo.')
        for i,p in enumerate(d):
            if progress: progress(i+1,len(d),name)
            raw=p.get_text(sort=False); lines=spatial_lines(p)
            page=Page(name,h,i+1,raw,lines)
            if len(re.sub(r'\s','',raw)) < 70:
                page.ocr=True
                if not ocr: page.error='Página sem texto; OCR desabilitado.'
                else:
                    try:
                        pix=p.get_pixmap(dpi=dpi,colorspace=fitz.csRGB)
                        img=Image.open(io.BytesIO(pix.tobytes('png')))
                        img=ImageOps.autocontrast(ImageOps.grayscale(img))
                        is_point=focus=='Ponto' or (not focus and classify_file(name)=='Ponto')
                        if is_point:img=img.crop((0,0,img.width,int(img.height*.30)))
                        langs=pytesseract.get_languages(config=''); lang='por+eng' if 'por' in langs else 'eng'
                        df=pytesseract.image_to_data(img,lang=lang,config='--psm 6' if is_point else '--psm 3',output_type=pytesseract.Output.DATAFRAME,timeout=55)
                        df=df.dropna(subset=['text']); df=df[df.conf>=0]
                        ol=[]
                        for _,g in df.groupby(['block_num','par_num','line_num'],sort=False): ol.append(' '.join(g.text.astype(str)))
                        page.lines=ol; page.text='\n'.join(ol)
                        page.confidence=round(float(df.conf.mean()),1) if len(df) else 0
                        if not ol: page.error='OCR sem texto legível.'
                    except Exception as exc: page.error=f'OCR falhou: {str(exc)[:180]}'
            cm=re.search(r'(?:Compet[eê]ncia\s*:?|Mensalidade\s*-)\s*(\d{2}/\d{4})',page.text,re.I)
            if cm: page.competence=cm.group(1)
            pages.append(page)
    return pages


def payroll(pages):
    people=[]; inherited_contract=''; company=''; cnpj=''; competence=''
    for p in pages:
        text='\n'.join(p.lines)
        cp=re.search(r'Empresa:\s*\d+\s*-\s*(.+?)(?:Página:|$)',text,re.M)
        if cp: company=cp.group(1).strip()
        cj=re.search(r'CNPJ:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',text)
        if cj: cnpj=cj.group(1)
        cm=re.search(r'Compet[eê]ncia:\s*(\d{2}/\d{4})',text,re.I)
        if cm: competence=cm.group(1)
        service=re.search(r'Serviço:\s*(.+?)(?:\s*-\s*CNPJ:|$)',text,re.M)
        if service: inherited_contract=service.group(1).strip()
        elif not inherited_contract:
            srv=re.search(r'Serviços:\s*(.+)',text)
            if srv: inherited_contract=srv.group(1).strip()
        matches=list(re.finditer(r'Empr\.:\s*(\d+)\s+(.+?)(?:\s+Situa[çc][aã]o:|\s+CPF:|$)',text,re.M|re.I))
        for idx,m in enumerate(matches):
            block=text[m.start():matches[idx+1].start() if idx+1<len(matches) else len(text)]
            cpfm=CPF_RE.search(block); cf=cpf_normalize(cpfm.group() if cpfm else '')
            name=m.group(2).strip()
            job=re.search(r'Cargo:\s*\d*\s*(.+?)(?:C\.B\.O:|$)',block,re.M)
            vt_lines=discount_lines(block,r'VALE\s+TRANSPORTE')
            un_lines=discount_lines(block,r'Sindilimpe')
            warnings=[]
            if not cpf_valid(cf): warnings.append('CPF da folha ausente ou inválido; revisar.')
            if p.ocr: warnings.append('Folha lida por OCR; validar cadastro e rubricas.')
            if not inherited_contract: warnings.append('Contrato não identificado.')
            if not plausible_name(name): warnings.append('Nome da folha exige validação.')
            person=Person(uid(cnpj,inherited_contract,competence,cf or m.group(1)),name,cf,m.group(1),company,cnpj,inherited_contract,competence,job.group(1).strip() if job else '',bool(vt_lines),bool(un_lines),p.file,p.number,block,warnings,[f'{p.file} · p.{p.number}'])
            people.append(person)
        p.layout='Folha Domínio' if matches else 'Resumo / página sem cadastro reconhecido'
        p.records=len(matches)
    grouped={}
    for e in people:
        if e.id not in grouped: grouped[e.id]=e
        else:
            old=grouped[e.id];old.sources+=e.sources
            if norm(old.name)!=norm(e.name) or old.vt!=e.vt or old.union!=e.union:
                old.warnings.append('Folhas repetidas com nome/rubricas divergentes; confirmar regras.')
            old.vt=old.vt or e.vt; old.union=old.union or e.union
    return list(grouped.values())


def classify_file(name,text=''):
    n=norm(name+' '+text[:800])
    if 'FOLHA DE PAGAMENTO' in n or ('EXTRATO MENSAL' in n and 'EMPR' in n): return 'Folha'
    if 'PONTO' in n or 'FREQUENCIA' in n: return 'Ponto'
    if 'ALVORADA' in n: return 'VT Alvorada'
    if 'TRANSPORTE' in n or 'GVBUS' in n: return 'VT GVBUS'
    if 'ALIMENTACAO' in n: return 'VA'
    if 'ODONTO' in n: return 'Odonto'
    if 'SAUDE' in n: return 'Saúde'
    if 'IDESBRE' in n: return 'Idesbre'
    if 'SINDICATO' in n: return 'Sindicato'
    if 'SEGURO DE VIDA' in n or 'RELACAO DE SEGURADOS' in n: return 'Seguro de vida'
    return 'Não classificado'


def month_hint(filename):
    match=re.search(r'(?<!\d)(0[1-9]|1[0-2])[./-](20\d{2})(?!\d)',filename)
    return match.group(1)+'/'+match.group(2) if match else ''

def assign_document_month(pages,records,declared):
    declared=str(declared).strip()
    if not declared:return
    if not re.fullmatch(r'(0[1-9]|1[0-2])/20\d{2}',declared):raise ValueError('Competência informada inválida: use MM/AAAA.')
    conflicts={r.competence for r in records if r.competence and r.competence!=declared}
    if conflicts:raise ValueError('Competência informada diverge do mês reconhecido no documento: '+', '.join(sorted(conflicts)))
    for r in records:
        if not r.competence:r.competence=declared
    for page in pages:
        if not page.competence:page.competence=declared

def parse_passepay_row(line):
    # Passepay/EvomPass: ID hexadecimal, nome, telefone, e-mail, crédito.
    # Telefone/e-mail nunca são tratados como CPF ou parte do nome.
    m=re.match(r'^([A-Fa-f0-9]{6,12})\s+(.+?)\s+(?:\+55\s*\(\d{2}\)|\+55\s+\d{2}|\(\d{2}\))\s*',line)
    value=re.search(r'R\$\s*(-?\d[\d.]*,\d{2})\s*$',line)
    if not m or not value or not plausible_name(m.group(2)):return None
    return m.group(1),m.group(2).strip(),float(value.group(1).replace('.','').replace(',','.'))

def parse_records(pages,benefit):
    out=[]; insurance_active=True; relation_seen=False; file_competence=''
    for p in pages:
        before=len(out); lines=p.lines; joined='\n'.join(lines); n=norm(joined)
        if p.error: p.layout='Leitura inconclusiva'; continue
        if benefit=='Ponto':
            header='\n'.join(lines[:35])
            cm=re.search(r'(?<![\d/])(\d{2}/\d{4})(?!\d)',header)
            months={'JANEIRO':'01','FEVEREIRO':'02','MARCO':'03','ABRIL':'04','MAIO':'05','JUNHO':'06','JULHO':'07','AGOSTO':'08','SETEMBRO':'09','OUTUBRO':'10','NOVEMBRO':'11','DEZEMBRO':'12'}
            if cm:p.competence=cm.group(1)
            else:
                for label,num in months.items():
                    month=re.search(label+r'\s*[/ -]\s*(20\d{2})',header,re.I)
                    if month:p.competence=num+'/'+month.group(1);break
            p.layout='Folha de ponto (OCR)' if p.ocr else 'Folha de ponto'
            for line in lines:
                m=re.search(r'Colaborador\s*:\s*(.+?)(?:\s+(?:Função|Funcao|Contrato|Código|Codigo|CPF)\s*:|$)',line,re.I)
                if m and plausible_name(m.group(1)):
                    out.append(Record(uid(p.file_hash,p.number,m.group(1)),benefit,m.group(1).strip(),'',p.file,p.number,line,p.ocr,p.confidence,True,p.competence))
            p.records=len(out)-before
            if not p.records:p.layout='Ponto: nome não identificado; revisão visual necessária'
            continue
        relation = ('MOVIMENTOS' in n if benefit in ['Sindicato','Idesbre'] else
                    'DEMONSTRATIVO ANALITICO' in n and 'CPF' in n if benefit=='Odonto' else
                    ('NR CPF' in n or 'RESUMO DO FATURAMENTO' in n) if benefit=='Seguro de vida' else
                    ('COD REFERENCIA NA EMPRESA' in n or 'DE PRE PAGAMENTO' in n) if benefit=='Saúde' else
                    ('CARTAO' in n and 'NOME' in n) if benefit in ['VT GVBUS','VT Alvorada','VA'] else False)
        if p.competence: file_competence=p.competence
        if not p.competence: p.competence=file_competence
        if benefit in ['VT GVBUS','VT Alvorada'] and any(re.match(r'^\d{10,16}\s+\d+\s+',line) for line in lines): relation=True
        if benefit=='VA' and any(re.match(r'^\d{4}[Xx*]+\d{4}\s+',line) for line in lines): relation=True
        passepay=benefit=='VT Alvorada' and any(parse_passepay_row(line) for line in lines)
        if passepay:relation=True
        if relation: relation_seen=True
        if not relation and benefit=='Saúde' and relation_seen and 'COD REFERENCIA' in n: relation=True
        if not relation:
            p.layout='Financeiro / não reconhecido como relação'
            continue
        p.layout='Relação Passepay/EvomPass · VT Alvorada' if passepay else f'Relação · {benefit}'
        for i,line in enumerate(lines):
            name=''; cf=''; reg=''; amount=None; active=True; warnings=[]
            nl=norm(line)
            if benefit=='Seguro de vida':
                if 'EXCLUSOES DO MES' in nl or 'EXCLUSAO DO MES' in nl: insurance_active=False
                if 'SEGURADOS DO MES ANTERIOR' in nl or 'INCLUSOES DO MES' in nl: insurance_active=True
                m=CPF_RE.search(line)
                if m and plausible_name(line[:m.start()]): name=line[:m.start()].strip();cf=cpf_normalize(m.group());active=insurance_active
            elif benefit=='Odonto':
                m=re.match(r'^\d[\d.]*-\d\s+(.+?)\s+(\d+)\s+(\d{7,11})\s+',line)
                if m:
                    name=m.group(1).strip();reg=m.group(2);cf=cpf_normalize(m.group(3))
                    if 'DEPENDENTE' in nl or re.search(r'\sD\s',line): active=False;warnings.append('Dependente: não comprova titular.')
                    if len(m.group(3))<11: warnings.append('CPF completado com zeros à esquerda.')
            elif benefit in ['Sindicato','Idesbre']:
                m=re.match(r'^(\d+)\s+(.+?)\s+(\d{2}/\d{4})\s+',line)
                if m and plausible_name(m.group(2)): reg=m.group(1);name=m.group(2).strip()
            elif benefit=='Saúde':
                # Cabeçalho do titular, não as linhas de dependentes/serviços.
                m=re.match(r'^(.+?)\s+C[oó]d\.\s*Refer[eê]ncia na Empresa\s*:',line,re.I)
                if m and plausible_name(m.group(1)): name=m.group(1).strip()
                elif i+1<len(lines) and 'COD REFERENCIA NA EMPRESA' in norm(lines[i+1]) and plausible_name(line): name=line.strip()
            elif benefit=='VA':
                m=re.match(r'^\d{4}[Xx*]+\d{4}\s+(.+?)(?=\s+\d|\s+R\$|$)',line)
                if m:
                    name=m.group(1).strip()
                    # Alguns relatórios têm centro de custo textual (SESA etc.).
                    name=re.sub(r'\s+(?:SESA|MATRIZ|PMVV)$','',name,flags=re.I)
                    amounts=re.findall(r'(?:R\$\s*)?(-?[\d.]+[,.]\d{2})',line)
                    if amounts:
                        raw=amounts[-1]; amount=float(raw.replace('.','').replace(',','.')) if ',' in raw else float(raw)
                        if amount<0:active=False;warnings.append('Valor VA negativo: revisar documento.')
                        elif amount==0:warnings.append('VA zerado: consta na relação. Saldo anterior do cartão não foi verificado.')
            elif benefit=='VT Alvorada' and parse_passepay_row(line):
                reg,name,amount=parse_passepay_row(line)
                if amount<=0:active=False;warnings.append('Carga de VT zero: presença não comprova crédito.')
            elif benefit in ['VT GVBUS','VT Alvorada']:
                m=re.match(r'^(\d{10,16})\s+(\d+)\s+(.+?)\s+('+MONEY+r')\s+('+MONEY+r')\s*$',line)
                if m:
                    reg=m.group(2);name=m.group(3).strip();amount=float(m.group(5).replace('.','').replace(',','.'))
                    # GVBUS quebra sobrenomes na linha seguinte.
                    for following in lines[i+1:i+3]:
                        if re.search(r'\d',following) or not re.fullmatch(r'[A-Za-zÀ-ÿ .]+',following.strip()): break
                        if set(norm(following).split()) & {'TOTAL','PAGINA','CARTAO','MATRICULA','NOME','SISTEMA'}: break
                        name+=' '+following.strip()
                    if amount<=0:active=False;warnings.append('Carga de VT zero: presença não comprova crédito.')
                elif benefit=='VT Alvorada':
                    m=re.match(r'^\d+\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .]+?)\s+('+MONEY+r')\s*$',line)
                    if m: name=m.group(1).strip();amount=float(m.group(2).replace('.','').replace(',','.'));active=amount>0;warnings.append('Layout Alvorada genérico: revisar.')
            if name and plausible_name(name):
                if cf and not cpf_valid(cf):warnings.append('CPF do documento inválido; exige revisão.')
                out.append(Record(uid(p.file_hash,p.number,i,benefit),benefit,name,cf,p.file,p.number,line,p.ocr,p.confidence,active,p.competence,amount,reg,warnings=warnings))
        p.records=len(out)-before
        if not p.records:p.layout='Relação reconhecida, mas nenhum registro extraído: revisar layout'
    if benefit=='Seguro de vida':
        excluded={r.cpf for r in out if not r.active and r.cpf}
        for r in out:
            if r.cpf in excluded:r.active=False;r.warnings.append('Consta nas exclusões do relatório; não confirma cobertura.')
    # Deduplica identidades, mas mantém todas as evidências em registros separados para auditoria.
    return out


def tokens(n): return [x for x in norm(n).split() if x not in {'DA','DE','DO','DAS','DOS','E'}]

def name_score(a,b):
    aa,bb=tokens(a),tokens(b)
    if not aa or not bb:return 0
    direct=fuzz.ratio(' '.join(aa),' '.join(bb))
    if len(aa)==len(bb):
        aligned=sum(96 if (len(x)==1 or len(y)==1) and x[0]==y[0] else fuzz.ratio(x,y) for x,y in zip(aa,bb))/len(aa)
        direct=max(direct,aligned)
    # Primeiro nome discordante reduz a confiança, mesmo com sobrenomes iguais.
    if aa[0]!=bb[0] and fuzz.ratio(aa[0],bb[0])<88:direct=min(direct,74)
    return round(direct,2)

def abbreviated_subset(a,b):
    # Nome encurtado na relação pode omitir sobrenomes inteiros. Sugere revisão,
    # nunca confirmação automática, mesmo quando a pontuação global é baixa.
    aa,bb=tokens(a),tokens(b)
    short,long=(aa,bb) if len(aa)<len(bb) else (bb,aa)
    if len(short)<2 or len(short)>=len(long) or short[0]!=long[0]:return False
    pos=0
    for word in short:
        hit=next((i for i in range(pos,len(long)) if word==long[i] or (len(word)==1 and word==long[i][0])),None)
        if hit is None:return False
        pos=hit+1
    return True

def safe_fuzzy(a,b):
    aa,bb=tokens(a),tokens(b)
    return len(aa)==len(bb) and len(aa)>=3 and aa[0]==bb[0] and aa[-1]==bb[-1] and all(len(x)>1 and len(y)>1 for x,y in zip(aa,bb)) and all(fuzz.ratio(x,y)>=80 for x,y in zip(aa,bb))


def reconcile(people,records,pages,vt_mode='Qualquer operadora',include_ponto=True,decisions=None,threshold=97):
    decisions=decisions or {}; results=[]; candidates={}; used=set(); owners=defaultdict(set)
    groups=defaultdict(list)
    for r in records:groups[r.benefit].append(r)
    provided={p.file for p in pages}
    page_by_file=defaultdict(list)
    for p in pages:page_by_file[p.file].append(p)
    by_id={r.id:r for r in records}
    pool_cache={}; name_cache={r.id:norm(r.name) for r in records}; token_cache={r.id:tokens(r.name) for r in records}; valid_cache={r.id:cpf_valid(r.cpf) for r in records}
    homonyms=defaultdict(set)
    for employee in people:homonyms[norm(employee.name)].add(employee.cpf or employee.id)
    for e in people:
        employee_name=norm(e.name); employee_tokens=tokens(e.name); employee_cpf_valid=cpf_valid(e.cpf)
        req=['VA','Saúde','Odonto','Seguro de vida','Idesbre']
        if e.union:req.append('Sindicato')
        if e.vt:req+=['VT GVBUS','VT Alvorada'] if vt_mode=='Ambas para guarda-vidas' and 'GUARDA' in norm(e.job) and 'VIDA' in norm(e.job) else ['VT']
        if include_ponto:req.append('Ponto')
        for b in ['VA','Saúde','Odonto','Seguro de vida','Idesbre','Sindicato','VT','Ponto'] + (['VT GVBUS','VT Alvorada'] if 'VT GVBUS' in req else []):
            if b=='Ponto' and not include_ponto:continue
            if b=='VT' and 'VT GVBUS' in req:continue
            row_id=uid(e.id,b); expected=b in req
            row={'id':row_id,'colaborador_id':e.id,'Colaborador':e.name,'CPF':e.cpf,'Empresa':e.company,'CNPJ':e.cnpj,'Contrato':e.contract,'Competência':e.competence,'Benefício':b,'Obrigatório':expected,'Status':'Não exigido','Nome documento':'','CPF documento':'','Similaridade':0.,'Método':'','Arquivo':'','Página':0,'Folha':e.file,'Página folha':e.page,'Observação':'','Revisor':'','Decisão em':'','Valor documento':None,'VA zerado':False}
            if not expected:results.append(row);continue
            is_guard='GUARDA' in norm(e.job) and 'VIDA' in norm(e.job)
            kinds=(['VT GVBUS','VT Alvorada'] if is_guard else ['VT GVBUS']) if b=='VT' else [b]
            cache_key=(tuple(kinds),e.cnpj,e.competence)
            if cache_key not in pool_cache:
                rs=[r for k in kinds for r in groups[k] if not r.company_cnpj or r.company_cnpj==e.cnpj]
                compatible=[r for r in rs if not r.competence or r.competence==e.competence]
                unique={}
                for r in compatible:
                    if not r.active:continue
                    key=(r.cpf if valid_cache[r.id] else name_cache[r.id],r.benefit)
                    better_va=r.benefit=='VA' and r.amount is not None and r.amount>0 and (unique[key].amount is None or unique[key].amount==0) if key in unique else False
                    if key not in unique or (unique[key].ocr and not r.ocr) or better_va:unique[key]=r
                pool_cache[cache_key]=(rs,compatible,list(unique.values()))
            rs,compatible,pool=pool_cache[cache_key]
            # Pré-filtro apenas para ranking por nome. CPF exato continua sendo procurado no pool completo.
            first=employee_tokens[0] if employee_tokens else ''
            ranking_pool=[r for r in pool if token_cache[r.id] and (token_cache[r.id][0][:1]==first[:1] or fuzz.ratio(first,token_cache[r.id][0])>=80)]
            ranked=sorted(((name_score(e.name,r.name),r) for r in ranking_pool),key=lambda t:t[0],reverse=True)
            candidates[row_id]=[{'id':r.id,'nome':r.name,'cpf':r.cpf,'score':s,'arquivo':r.file,'pagina':r.page,'evidencia':r.evidence} for s,r in ranked[:5]]
            chosen=None;status='';method='';score=0.;obs=[]
            exactcpf=[r for r in pool if employee_cpf_valid and r.cpf==e.cpf and valid_cache[r.id]]
            exactname=[r for r in pool if name_cache[r.id]==employee_name]
            if exactcpf:
                chosen=exactcpf[0];score=name_score(e.name,chosen.name);method='CPF válido idêntico';status='Confirmado'
                if score<75:status='Revisar';obs.append('CPF coincide, mas nome muito divergente.')
            elif exactname:
                chosen=exactname[0];score=100.;method='Nome normalizado idêntico';status='Confirmado'
                if len({r.cpf for r in exactname if r.cpf})>1:status='Revisar';obs.append('Homônimo com CPFs diferentes no documento.')
                if chosen.cpf and (not cpf_valid(chosen.cpf) or (e.cpf and chosen.cpf!=e.cpf)):status='Conflito CPF';obs.append('Nome igual não sobrepõe CPF divergente/ inválido.')
                if len(homonyms[employee_name])>1:status='Revisar';obs.append('Homônimo na folha; nome sozinho não basta.')
            elif ranked and (ranked[0][0]>=72 or abbreviated_subset(e.name,ranked[0][1].name)):
                score,chosen=ranked[0];margin=score-(ranked[1][0] if len(ranked)>1 else 0);method='Proximidade de nomes'
                status='Confirmado' if score>=threshold and margin>=7 and safe_fuzzy(e.name,chosen.name) else 'Revisar'
                obs.append(f'Índice de similaridade {score:.1f}; distância do 2º candidato {margin:.1f}. Não é probabilidade.')
                if score<72:obs.append('Nome encurtado com palavras em comum na mesma ordem; revisão individual obrigatória.')
                if chosen.cpf and (not cpf_valid(chosen.cpf) or (e.cpf and chosen.cpf!=e.cpf)):status='Conflito CPF'
            else:
                status='Não localizado'
                if not rs:status='Documento ausente ou sem relação legível'
                if rs and not compatible:status='Competência divergente'
                record_files={r.file for r in rs}
                relatedfiles={p.file for p in pages if p.layout.endswith(tuple(kinds)) or p.file in record_files}
                if b=='Ponto' or any(p.error or p.ocr for f in relatedfiles for p in page_by_file[f]):status='Leitura inconclusiva' if status=='Não localizado' else status
            if chosen:
                if chosen.ocr or chosen.warnings:obs+=chosen.warnings
                if chosen.ocr:status='Revisar';obs.append('Correspondência de OCR exige confirmação visual; manuscrito não é validado automaticamente.')
                if any('Layout Alvorada genérico' in w for w in chosen.warnings):status='Revisar'
                if chosen.competence and chosen.competence!=e.competence:status='Competência divergente'
            decision=decisions.get(row_id)
            if decision:
                action=decision.get('action','')
                if action=='confirm':
                    chosen=by_id.get(decision.get('record_id'));status='Validado manualmente' if chosen else 'Revisar';method='Revisão humana'
                    if chosen:
                        score=name_score(e.name,chosen.name)
                        if chosen.benefit not in kinds or not chosen.active or (chosen.company_cnpj and chosen.company_cnpj!=e.cnpj) or (chosen.competence and chosen.competence!=e.competence):
                            status='Revisar';obs.append('Vínculo manual incompatível com benefício, empresa, competência ou registro inativo.')
                elif action=='missing':chosen=None;status='Ausência confirmada';method='Revisão humana'
                elif action=='waive':chosen=None;status='Dispensa justificada';method='Revisão humana'
                elif action=='clear':chosen=None;status='Revisar';method='Vínculo removido';obs.append('Vínculo removido pelo conferente; exige nova revisão.')
                obs.append(decision.get('note',''));row['Revisor']=decision.get('reviewer','');row['Decisão em']=decision.get('at','')
            if e.warnings:obs+=e.warnings
            if e.warnings and status=='Confirmado':status='Revisar'
            row.update({'Status':status,'Similaridade':score,'Método':method,'Observação':' | '.join(dict.fromkeys(x for x in obs if x))})
            if chosen:
                row.update({'Nome documento':chosen.name,'CPF documento':chosen.cpf,'Arquivo':chosen.file,'Página':chosen.page,'registro_id':chosen.id,'Valor documento':chosen.amount,'VA zerado':b=='VA' and chosen.amount==0})
                if status in ['Confirmado','Validado manualmente']:
                    key=(chosen.benefit,chosen.cpf if cpf_valid(chosen.cpf) else norm(chosen.name))
                    owners[key].add(e.cpf or e.id);used.add(chosen.id)
            results.append(row)
    # Impede que um mesmo registro confirme duas pessoas diferentes.
    for row in results:
        r=by_id.get(row.get('registro_id'))
        if r:
            key=(r.benefit,r.cpf if cpf_valid(r.cpf) else norm(r.name))
            if len(owners[key])>1 and row['Status'] in ['Confirmado','Validado manualmente']:
                row['Status']='Revisar';row['Observação']+=' | Registro disputado por colaboradores diferentes.'
    matched_keys={(by_id[row['registro_id']].benefit,by_id[row['registro_id']].cpf or norm(by_id[row['registro_id']].name)) for row in results if row.get('registro_id') and row['Status'] in ['Confirmado','Validado manualmente']}
    outside=[asdict(r) for r in records if r.active and (r.benefit,r.cpf or norm(r.name)) not in matched_keys]
    return results,candidates,outside
