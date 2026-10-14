"""Marca-texto PDF nativo. Nunca remove/reordena páginas ou grava sobre a origem."""
import io,zipfile,csv,re,unicodedata,hashlib
from dataclasses import dataclass
import pymupdf as fitz
from engine import norm,cpf_valid
from document_layout import rows_from_words

CONFIRMED={'Confirmado','Validado manualmente'}
FINISHED=CONFIRMED|{'Dispensa justificada','Não exigido','Ausência confirmada'}


def locate_name_boxes(page,name,evidence=''):
    existing=getattr(page,'words',[])
    target=[norm(x) for x in name.split() if norm(x)]
    if not target or not existing:return []
    rows=rows_from_words(existing,getattr(page,'rotation',0),getattr(page,'width',0),getattr(page,'height',0))
    expected=norm(evidence)
    for rid,row in enumerate(rows):
        line=norm(' '.join(w['text'] for w in row))
        # A evidência de origem ancora a linha correta e evita marcar homônimos
        # ou um nome maior que apenas contém o trecho procurado.
        if expected and line!=expected and not (line==norm(name)):continue
        words=[w for w in row if norm(w['text'])]
        values=[norm(w['text']) for w in words]
        for start,value in enumerate(values):
            if value!=target[0]:continue
            take=[];at=start;idx=0
            while at<len(words) and idx<len(target) and values[at]==target[idx]:take.append(words[at]);at+=1;idx+=1
            if not take:continue
            # Sobrenome quebrado na linha seguinte; restringe ao campo do nome.
            if idx<len(target) and rid+1<len(rows):
                x=take[0]['visual'][0]
                nextwords=[w for w in rows[rid+1] if x-8<=w['visual'][0] and norm(w['text'])]
                for word in nextwords:
                    if idx>=len(target):break
                    if norm(word['text'])!=target[idx]:break
                    take.append(word);idx+=1
            if idx==len(target):return [w['box'] for w in take]
    return []


def collaborator_field_box(page):
    """Campo Colaborador em ponto já vinculado visualmente; não decifra caneta."""
    rows=rows_from_words(getattr(page,'words',[]),getattr(page,'rotation',0),getattr(page,'width',0),getattr(page,'height',0))
    for row in rows:
        label=next((w for w in row if norm(w['text'])=='COLABORADOR'),None)
        if not label:continue
        v=label['visual'];limit=next((w['visual'][0]-3 for w in row if w['visual'][0]>v[2] and norm(w['text']) in {'CPF','CNPJ','FUNCAO','CONTRATO','HORARIO'}),None)
        width=page.height if page.rotation in [90,270] else page.width
        right=limit or width*.93
        if right<=v[2]+5:return []
        # Conversão para coordenadas nativas de anotação.
        rect=fitz.Rect(v[2]+3,v[1]-1,right,v[3]+3)
        if page.rotation==90:rect=fitz.Rect(rect.y0,page.height-rect.x1,rect.y1,page.height-rect.x0)
        elif page.rotation==180:rect=fitz.Rect(page.width-rect.x1,page.height-rect.y1,page.width-rect.x0,page.height-rect.y0)
        elif page.rotation==270:rect=fitz.Rect(page.width-rect.y1,rect.x0,page.width-rect.y0,rect.x1)
        return [list(rect)]
    return []


def _eligible_records(people,records,rows):
    byperson={e.id:e for e in people};byrecord={r.id:r for r in records};result={}
    for row in rows:
        if not row.get('Obrigatório') or row['Status'] not in CONFIRMED:continue
        chosen=byrecord.get(row.get('registro_id'));employee=byperson.get(row['colaborador_id'])
        if not chosen or not employee:continue
        for r in records:
            if r.benefit!=chosen.benefit or not r.active:continue
            if r.company_cnpj and r.company_cnpj!=employee.cnpj:continue
            if r.competence and r.competence!=employee.competence:continue
            same=r.id==chosen.id or (cpf_valid(r.cpf) and r.cpf==employee.cpf) or (norm(r.name)==norm(chosen.name) and (not r.cpf or r.cpf==employee.cpf))
            if same:result[r.id]=(r,employee)
    return list(result.values())


def marked_pdf_zip(blobs,people,records,pages,rows,progress=None):
    unresolved=[r for r in rows if r.get('Obrigatório') and r['Status'] not in FINISHED]
    if unresolved:raise ValueError(f'{len(unresolved)} conferências ainda sem conclusão. Resolva/revise ou confirme a ausência antes do ZIP final.')
    pagesmap={(p.file,p.number):p for p in pages};targets={}
    for record,employee in _eligible_records(people,records,rows):targets.setdefault(record.file,[]).append((record,employee))
    original_targets={name:list(items) for name,items in targets.items()}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in blobs.items()}
    for current in blobs:
        for source,items in original_targets.items():
            if current==source or hashes.get(current)!=hashes.get(source):continue
            for record,employee in items:
                info=pagesmap.get((current,record.page))
                if info and info.competence and info.competence!=employee.competence:continue
                targets.setdefault(current,[]).append((record,employee))
    buf=io.BytesIO();audit=[];used_names=set()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
        for idx,(filename,data) in enumerate(blobs.items()):
            if progress:progress(idx+1,len(blobs),filename)
            # Nomes mantidos. Se houver arquivos homônimos, separa pastas, não renomeia o PDF.
            name=filename.replace('\\','/').replace(' / ','/')
            parts=[part for part in name.split('/') if part not in {'','.', '..'}]
            name='/'.join(parts) or 'documento.pdf'
            if name in used_names:
                n=2
                while f'entrada_{n}/{name}' in used_names:n+=1
                name=f'entrada_{n}/{name}'
            used_names.add(name)
            with fitz.open(stream=data,filetype='pdf') as doc:
                count=len(doc);before_text=[p.get_text() for p in doc];before_rot=[p.rotation for p in doc]
                done=set();changed=False
                for record,employee in targets.get(filename,[]):
                    page_info=pagesmap.get((filename,record.page)) or pagesmap.get((record.file,record.page))
                    if page_info and not getattr(page_info,'words',[]):page_info=pagesmap.get((record.file,record.page),page_info)
                    if not page_info or not 1<=record.page<=count:
                        audit.append([filename,record.page,record.name,employee.name,'SEM MARCAÇÃO','Página não disponível']);continue
                    boxes=list(getattr(record,'boxes',[]) or [])
                    method='Caixas do nome na relação'
                    if not boxes:boxes=locate_name_boxes(page_info,record.name,record.evidence);method='Texto/posição da linha reconhecida'
                    if not boxes and record.benefit=='Ponto':boxes=collaborator_field_box(page_info);method='Campo Colaborador em página vinculada visualmente'
                    if not boxes:
                        audit.append([filename,record.page,record.name,employee.name,'SEM MARCAÇÃO','Nome não localizado geometricamente; revisar o PDF escaneado/área do nome.']);continue
                    page=doc[record.page-1];valid=[]
                    existing=[]
                    for old in page.annots() or []:
                        if old.type[0]==fitz.PDF_ANNOT_HIGHLIGHT:existing.append(fitz.Rect(old.rect))
                    for raw in boxes:
                        rect=fitz.Rect(raw)
                        # Origem nativa do PDF, sem limitar por page.rect rotacionado.
                        native=fitz.Rect(0,0,page.cropbox.width,page.cropbox.height)
                        rect=rect & native
                        if rect.is_empty or rect.width<=0 or rect.height<=0:continue
                        key=(record.page,tuple(round(x,2) for x in rect))
                        if key in done:continue
                        covered=any(box.contains(rect.tl) and box.contains(rect.br) for box in existing)
                        done.add(key)
                        if covered:continue
                        valid.append(rect)
                    if not valid:
                        audit.append([filename,record.page,record.name,employee.name,'JÁ MARCADO','Marca repetida consolidada ou marca-texto original preservado']);continue
                    annotation=page.add_highlight_annot(valid);annotation.set_colors(stroke=(1,0.85,0));annotation.set_opacity(.32)
                    annotation.set_info(title='Lider Limpe · conferência interna',content=f'{employee.name} | {record.benefit} | {method}');annotation.update();changed=True
                    audit.append([filename,record.page,record.name,employee.name,'MARCADO',method])
                result=doc.tobytes(garbage=0,deflate=True,encryption=fitz.PDF_ENCRYPT_KEEP) if changed else data
            with fitz.open(stream=result,filetype='pdf') as verified:
                if len(verified)!=count or [p.rotation for p in verified]!=before_rot or [p.get_text() for p in verified]!=before_text:raise ValueError('Falha na preservação das páginas/conteúdo: '+filename)
            archive.writestr(name,result)
        report=io.StringIO();writer=csv.writer(report,delimiter=';');writer.writerow(['Arquivo','Página','Nome na relação','Nome da folha','Resultado','Como foi localizado'])
        for line in audit:writer.writerow(["'"+str(value) if str(value).lstrip().startswith(('=','+','-','@')) else value for value in line])
        archive.writestr('CONTROLE_MARCACOES.csv',('\ufeff'+report.getvalue()).encode('utf-8'))
    return buf.getvalue(),audit
