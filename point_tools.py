"""Estado da mesa de ponto: funções puras, sem dependência de Streamlit."""
from engine import uid,norm,Record

POINT_DONE={'Confirmado','Validado manualmente','Dispensa justificada'}

def point_workspace(people,pages,records,rows,categories=None):
    categories=categories or {}
    employees={e.id:e for e in people}
    point_rows={r['colaborador_id']:r for r in rows if r['Benefício']=='Ponto' and r['colaborador_id'] in employees}
    pending=sorted([e for e in people if point_rows.get(e.id,{}).get('Status') not in POINT_DONE],key=lambda e:(norm(e.name),e.competence,e.contract))
    completed=sorted([e for e in people if point_rows.get(e.id,{}).get('Status') in POINT_DONE],key=lambda e:(norm(e.name),e.competence,e.contract))
    recordmap={r.id:r for r in records};bindings={}
    for row in point_rows.values():
        if row['Status'] not in {'Confirmado','Validado manualmente'}:continue
        r=recordmap.get(row.get('registro_id',''))
        if r:bindings.setdefault((r.file,r.page),[]).append(employees[row['colaborador_id']])
    pointfiles={r.file for r in records if r.benefit=='Ponto'}|{p.file for p in pages if p.layout.startswith(('Folha de ponto','Ponto:'))}|{f for f,cat in categories.items() if cat=='Ponto'}
    candidates=[p for p in pages if p.file in pointfiles]
    def compatible(page):
        if page.competence and page.competence not in {e.competence for e in people}:return False
        owners={r.company_cnpj for r in records if r.benefit=='Ponto' and r.file==page.file and r.company_cnpj}
        return not owners or bool(owners & {e.cnpj for e in people})
    pgs=[p for p in candidates if compatible(p)]
    # Ordem de upload/arquivo e número de página, sem presumir identidade por ordem alfabética.
    unique={uid(p.file_hash,p.number):p for p in pgs}
    return pending,completed,list(unique.values()),bindings,point_rows

def validate_point_link(employee,page,records,rows):
    if page.competence and page.competence!=employee.competence:raise ValueError('A competência da página difere da folha selecionada.')
    byid={r.id:r for r in records}
    for row in rows:
        if row['Benefício']!='Ponto' or row['Status'] not in {'Confirmado','Validado manualmente'}:continue
        r=byid.get(row.get('registro_id',''))
        if r and r.file==page.file and r.page==page.number and row['colaborador_id']!=employee.id:raise ValueError('Esta página já está vinculada a outro colaborador. Remova o vínculo anterior.')
    owners={r.company_cnpj for r in records if r.file==page.file and r.benefit=='Ponto' and r.company_cnpj}
    if owners and employee.cnpj not in owners:raise ValueError('Esta página pertence a outra empresa.')

def manual_point_record(employee,page,note):
    return Record(uid('manual',page.file_hash,page.number,employee.id),'Ponto',employee.name,employee.cpf,page.file,page.number,note,True,100,True,page.competence or employee.competence,company_cnpj=employee.cnpj)
