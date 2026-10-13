from __future__ import annotations
import io, json, html, zipfile
from datetime import datetime, timezone
from dataclasses import asdict
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table,TableStyleInfo

GOOD={'Confirmado','Validado manualmente','Dispensa justificada','Não exigido'}
COLORS={'Confirmado':'DBF2E4','Validado manualmente':'D8EBFA','Revisar':'FFF1CB','Conflito CPF':'FBDDDD','Não localizado':'FBDDDD','Ausência confirmada':'FBDDDD','Leitura inconclusiva':'FFF1CB','Dispensa justificada':'E7E2F8','Não exigido':'EDF0F5'}

def frame(rows):return pd.DataFrame(rows)

def matrix(rows,mask=False):
    df=frame(rows)
    if df.empty:return df
    idx=['Empresa','Contrato','Competência','Colaborador','CPF']
    out=df.pivot_table(index=idx,columns='Benefício',values='Status',aggfunc='first',dropna=True).reset_index()
    out.columns.name=None
    if mask:out['CPF']=out['CPF'].apply(mask_cpf)
    return out

def mask_cpf(v):return ('***.'+v[3:6]+'.***-**') if isinstance(v,str) and len(v)==11 else ''

def safe_cell(v):
    if v is None:return ''
    if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
    if isinstance(v,str):
        v=v[:32000]
        if v.lstrip().startswith(('=','+','-','@')):v="'"+v
    return v

def workbook(rows,people=(),records=(),pages=(),decisions=None,client=False,meta=None,base_audit=None):
    df=frame(rows);wb=Workbook();wb.remove(wb.active);tables=0
    def add(title,data):
        nonlocal tables
        ws=wb.create_sheet(title[:31]);data=pd.DataFrame(data)
        if data.empty:ws.append(['Nenhum registro']);return
        ws.append(list(data.columns))
        for vals in data.itertuples(index=False,name=None):ws.append([safe_cell(x) for x in vals])
        ws.freeze_panes='A2';ws.sheet_view.showGridLines=False
        ws.row_dimensions[1].height=28
        for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='072F6B');c.alignment=Alignment(vertical='center')
        for j,col in enumerate(data.columns,1):
            width=min(64,max(14,len(str(col))+2,max((len(str(x)) for x in data.iloc[:150,j-1]),default=12)+2))
            ws.column_dimensions[get_column_letter(j)].width=width
            for colcells in ws.iter_cols(min_col=j,max_col=j,min_row=2):
                for c in colcells:
                    c.alignment=Alignment(vertical='top',wrap_text=len(str(c.value))>55)
                    if 'CPF' in str(col):c.number_format='@'
                    if isinstance(c.value,str) and c.value in COLORS:c.fill=PatternFill('solid',fgColor=COLORS[c.value])
        tables+=1;tab=Table(displayName=f'Tabela{tables}',ref=f'A1:{get_column_letter(len(data.columns))}{len(data)+1}')
        tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);ws.add_table(tab)
        ws.auto_filter.ref=tab.ref
    summary=[]
    if not df.empty:
        for benefit,g in df[df['Obrigatório']].groupby('Benefício'):
            summary.append({'Benefício':benefit,'Conferências exigidas':len(g),'Confirmadas/dispensadas':g.Status.isin(GOOD).sum(),'Pendências':(~g.Status.isin(GOOD)).sum()})
    add('Resumo',summary);add('Matriz geral',matrix(rows,mask=client))
    cols=['Colaborador','CPF','Contrato','Competência','Benefício','Status','Nome documento','Similaridade','Método','Arquivo','Página','Observação','Revisor','Decisão em']
    detail=df[[c for c in cols if c in df.columns]].copy() if not df.empty else df
    if client and not detail.empty:
        detail['CPF']=detail['CPF'].apply(mask_cpf)
        detail=detail[['Colaborador','CPF','Contrato','Competência','Benefício','Status','Método']]
    add('Divergências',detail[~df.Status.isin(GOOD)] if not df.empty else [])
    for b in df['Benefício'].unique() if not df.empty else []:add(b,detail[df['Benefício']==b])
    if not client:
        add('Cadastro folha',[{k:v for k,v in asdict(e).items() if k!='evidence'} for e in people])
        add('Auditoria documentos',[{k:v for k,v in asdict(r).items() if k!='evidence'} for r in records])
        add('Auditoria páginas',[{'Arquivo':p.file,'Página':p.number,'Layout':p.layout,'Registros':p.records,'OCR':p.ocr,'Confiança OCR':p.confidence,'Erro':p.error,'Competência':p.competence,'SHA256':p.file_hash} for p in pages])
        add('Decisões humanas',[{'conferencia_id':k,**v} for k,v in (decisions or {}).items()])
        add('Ajustes cadastro',base_audit or [])
    add('Metadados',[{'Campo':k,'Valor':v} for k,v in (meta or {}).items()]+[{'Campo':'Gerado UTC','Valor':datetime.now(timezone.utc).isoformat()},{'Campo':'Escopo','Valor':'Presença em relações; não comprova pagamento, cobertura contratual vigente ou validade fiscal. Ponto: presença da folha, não valida jornada.'}])
    buf=io.BytesIO();wb.save(buf);return buf.getvalue()

def client_html(rows,contract_label='Lider Limpe',meta=None):
    df=frame(rows);pending=int((~df.Status.isin(GOOD)).sum()) if not df.empty else 0
    status='CONFERÊNCIA COM PENDÊNCIAS' if pending else 'CONFERÊNCIA CONCLUÍDA NO ESCOPO DOCUMENTAL'
    esc=lambda x:html.escape(str(x))
    table=matrix(rows,mask=True).to_html(index=False,escape=True,border=0) if rows else ''
    return f'''<!DOCTYPE html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Conferência documental</title><style>body{{font:14px Arial;background:#f3f6fa;color:#16335b;margin:0;padding:32px}}main{{background:white;padding:32px;border-radius:20px;max-width:1500px;margin:auto}}h1{{color:#072f6b}}.badge{{background:#fff0db;border-left:5px solid #f57c00;padding:18px}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:24px 0}}th{{background:#072f6b;color:white}}td,th{{padding:10px;border:1px solid #e5eaf1;text-align:left}}tr:nth-child(even){{background:#f6f8fc}}small{{color:#667}}@media print{{body{{padding:0;background:white}}main{{padding:8px}}table{{font-size:9px}}}}</style><main><h1>Lider Limpe · Conferência documental</h1><p>{esc(contract_label)}</p><div class="badge"><strong>{status}</strong><br>{pending} pendência(s). Resultado sujeito às fontes e às revisões registradas.</div>{table}<p>Esta conferência verifica a presença dos colaboradores nas relações enviadas. Não constitui liberação fiscal, comprovação de pagamento ou garantia de cobertura vigente. Folhas de ponto são conferidas somente quanto à identificação/presença, não à jornada.</p><small>Gerado em {esc(datetime.now(timezone.utc).isoformat())} · CPFs parcialmente mascarados · Dados pessoais: encaminhar somente ao destinatário autorizado.</small></main></html>'''

def client_package(rows,label,meta=None):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('conferencia_cliente.xlsx',workbook(rows,client=True,meta=meta))
        z.writestr('relatorio_cliente.html',client_html(rows,label,meta))
    return buf.getvalue()
