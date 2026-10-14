from __future__ import annotations
import io,json,html,zipfile,re,math,numbers
from datetime import datetime,timezone
from dataclasses import asdict
import pandas as pd
import xlsxwriter

GOOD={'Confirmado','Validado manualmente','Dispensa justificada','Não exigido'}
COLORS={'Confirmado':'DBF2E4','Validado manualmente':'D8EBFA','Revisar':'FFF1CB','Conflito CPF':'FBDDDD','Não localizado':'FBDDDD','Ausência confirmada':'FBDDDD','Leitura inconclusiva':'FFF1CB','Dispensa justificada':'E7E2F8','Não exigido':'EDF0F5'}

def frame(rows):return pd.DataFrame(rows)

def matrix(rows,mask=False):
    df=frame(rows)
    if df.empty:return df
    df=df.copy()
    if 'VA zerado' in df:
        zeros=(df['Benefício']=='VA') & df['VA zerado'].fillna(False).astype(bool)
        df.loc[zeros,'Status']=df.loc[zeros,'Status']+' · VA zerado'
    idx=['Empresa','Contrato','Competência','Colaborador','CPF']
    out=df.pivot_table(index=idx,columns='Benefício',values='Status',aggfunc='first',dropna=True).reset_index()
    out.columns.name=None
    if mask:out['CPF']=out['CPF'].apply(mask_cpf)
    return out

def mask_cpf(v):return ('***.'+v[3:6]+'.***-**') if isinstance(v,str) and len(v)==11 else ''

def safe_cell(v):
    if v is None:return ''
    if isinstance(v,(dict,list,tuple,set)):v=json.dumps(list(v) if isinstance(v,set) else v,ensure_ascii=False,default=str)
    if hasattr(v,'item') and not isinstance(v,str):
        try:v=v.item()
        except (ValueError,AttributeError):pass
    if isinstance(v,numbers.Real) and not math.isfinite(v):return ''
    if not isinstance(v,(str,numbers.Number,bool)):
        try:
            if pd.isna(v):return ''
        except (ValueError,TypeError):pass
        v=str(v)
    if isinstance(v,str):
        v=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]','',v)[:32000]
        if v.lstrip().startswith(('=','+','-','@')):v="'"+v
    return v

def workbook(rows,people=(),records=(),pages=(),decisions=None,client=False,meta=None,base_audit=None,decision_history=None):
    # XLSX padrão, sem tabelas estruturadas/metadados de Table nem proteção.
    # Fórmulas e URLs automáticas estão desabilitadas; campos são dados, não código.
    df=frame(rows);buf=io.BytesIO()
    wb=xlsxwriter.Workbook(buf,{'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False,'nan_inf_to_errors':False})
    wb.set_properties({'title':'Conferência documental Lider Limpe','author':'Lider Limpe','comments':'Exportação compatível, células editáveis. Não aprova faturamento.'})
    header=wb.add_format({'bold':True,'font_color':'#FFFFFF','bg_color':'#072F6B','text_wrap':True,'valign':'vcenter','border':0})
    normal=wb.add_format({'valign':'top','text_wrap':True})
    alternate=wb.add_format({'valign':'top','text_wrap':True,'bg_color':'#F4F7FB'})
    textformat=wb.add_format({'num_format':'@','valign':'top','text_wrap':True})
    currency=wb.add_format({'num_format':'#,##0.00','valign':'top'})
    statusfmt={status:wb.add_format({'bg_color':'#'+color,'valign':'top','text_wrap':True}) for status,color in COLORS.items()}
    titles=set()
    def add(title,data):
        data=pd.DataFrame(data)
        base=re.sub(r'[\[\]:*?/\\]',' ',str(title)).strip().strip("'")[:31] or 'Dados';title=base;n=2
        while title.casefold() in titles:title=base[:27]+' '+str(n);n+=1
        titles.add(title.casefold());ws=wb.add_worksheet(title);ws.hide_gridlines(2)
        if data.empty:ws.write_string(0,0,'Nenhum registro',normal);ws.set_column(0,0,40);return
        cols=[];seen=set()
        for i,col in enumerate(data.columns):
            name=str(safe_cell(str(col))).strip() or 'Coluna '+str(i+1);original=name;n=2
            while name.casefold() in seen:name=original+' '+str(n);n+=1
            seen.add(name.casefold());cols.append(name);ws.write_string(0,i,name,header)
        ws.set_row(0,32);ws.freeze_panes(1,0);ws.autofilter(0,0,len(data),len(cols)-1)
        for j,col in enumerate(cols):
            width=min(64,max(14,len(col)+2,max((min(len(str(x)),62) for x in data.iloc[:150,j]),default=12)+2))
            ws.set_column(j,j,width,textformat if 'cpf' in col.lower() else None)
        for ri,vals in enumerate(data.itertuples(index=False,name=None),1):
            for ci,raw in enumerate(vals):
                value=safe_cell(raw);fmt=alternate if ri%2==0 else normal
                if isinstance(value,str):
                    base_status=value.split(' · ')[0];fmt=statusfmt.get(base_status,fmt)
                    if 'cpf' in cols[ci].lower():fmt=textformat
                    ws.write_string(ri,ci,value,fmt)
                elif isinstance(value,bool):ws.write_boolean(ri,ci,value,fmt)
                elif isinstance(value,numbers.Number):ws.write_number(ri,ci,float(value),currency if 'valor' in cols[ci].lower() else fmt)
                else:ws.write_string(ri,ci,str(value),fmt)
        ws.set_landscape();ws.fit_to_pages(1,0);ws.repeat_rows(0);ws.set_footer('&LLider Limpe · conferência documental&R Página &P de &N')
    summary=[]
    if not df.empty:
        for benefit,g in df[df['Obrigatório']].groupby('Benefício'):
            summary.append({'Benefício':benefit,'Conferências exigidas':len(g),'Confirmadas/dispensadas':int(g.Status.isin(GOOD).sum()),'Pendências':int((~g.Status.isin(GOOD)).sum()),'VA zerado':int(g.get('VA zerado',pd.Series(False,index=g.index)).fillna(False).sum()) if benefit=='VA' else 0})
    add('Resumo',summary);add('Matriz geral',matrix(rows,mask=client))
    cols=['Colaborador','CPF','Contrato','Competência','Benefício','Status','VA zerado','Valor documento','Nome documento','Similaridade','Método','Arquivo','Página','Observação','Revisor','Decisão em']
    detail=df[[c for c in cols if c in df.columns]].copy() if not df.empty else df
    if client and not detail.empty:
        detail['CPF']=detail['CPF'].apply(mask_cpf)
        detail=detail[[c for c in ['Colaborador','CPF','Contrato','Competência','Benefício','Status','VA zerado','Método'] if c in detail]]
    add('Divergências',detail[~df.Status.isin(GOOD)] if not df.empty else [])
    for b in df['Benefício'].unique() if not df.empty else []:add(b,detail[df['Benefício']==b])
    if not client:
        add('Cadastro folha',[{k:v for k,v in asdict(e).items() if k!='evidence'} for e in people])
        add('Auditoria documentos',[{k:v for k,v in asdict(r).items() if k!='evidence'} for r in records])
        add('Auditoria páginas',[{'Arquivo':p.file,'Página':p.number,'Layout':p.layout,'Registros':p.records,'OCR':p.ocr,'Confiança OCR':p.confidence,'Erro':p.error,'Competência':p.competence,'SHA256':p.file_hash} for p in pages])
        add('Decisões humanas',[{'conferencia_id':k,**v} for k,v in (decisions or {}).items()])
        add('Histórico de decisões',decision_history or [])
        add('Ajustes cadastro',base_audit or [])
    add('Metadados',[{'Campo':k,'Valor':v} for k,v in (meta or {}).items()]+[{'Campo':'Gerado UTC','Valor':datetime.now(timezone.utc).isoformat()},{'Campo':'Exportador','Valor':'XlsxWriter; sem proteção; sem tabelas estruturadas; dados editáveis.'},{'Campo':'Escopo','Valor':'Presença em relações; VA zero é aceito com identificação segura, sem verificar saldo anterior. Não comprova pagamento, cobertura vigente ou validade fiscal. Ponto: presença da folha, não valida jornada.'}])
    wb.close();return buf.getvalue()

def client_html(rows,contract_label='Lider Limpe',meta=None):
    df=frame(rows);pending=int((~df.Status.isin(GOOD)).sum()) if not df.empty else 0
    status='CONFERÊNCIA COM PENDÊNCIAS' if pending else 'CONFERÊNCIA CONCLUÍDA NO ESCOPO DOCUMENTAL'
    esc=lambda x:html.escape(str(x))
    table=matrix(rows,mask=True).to_html(index=False,escape=True,border=0) if rows else ''
    return f'''<!DOCTYPE html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Conferência documental</title><style>body{{font:14px Arial;background:#f3f6fa;color:#16335b;margin:0;padding:32px}}main{{background:white;padding:32px;border-radius:20px;max-width:1500px;margin:auto}}h1{{color:#072f6b}}.badge{{background:#fff0db;border-left:5px solid #f57c00;padding:18px}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:24px 0}}th{{background:#072f6b;color:white}}td,th{{padding:10px;border:1px solid #e5eaf1;text-align:left}}tr:nth-child(even){{background:#f6f8fc}}small{{color:#667}}@media print{{body{{padding:0;background:white}}main{{padding:8px}}table{{font-size:9px}}}}</style><main><h1>Lider Limpe · Conferência documental</h1><p>{esc(contract_label)}</p><div class="badge"><strong>{status}</strong><br>{pending} pendência(s). Resultado sujeito às fontes e às revisões registradas.</div>{table}<p>VA zerado indica presença na relação com crédito zero; o saldo anterior do cartão não foi consultado. Esta conferência verifica a presença dos colaboradores nas relações enviadas. Não constitui liberação fiscal, comprovação de pagamento ou garantia de cobertura vigente. Folhas de ponto são conferidas somente quanto à identificação/presença, não à jornada.</p><small>Gerado em {esc(datetime.now(timezone.utc).isoformat())} · CPFs parcialmente mascarados · Dados pessoais: encaminhar somente ao destinatário autorizado.</small></main></html>'''

def client_package(rows,label,meta=None):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('conferencia_cliente.xlsx',workbook(rows,client=True,meta=meta))
        z.writestr('relatorio_cliente.html',client_html(rows,label,meta))
    return buf.getvalue()
