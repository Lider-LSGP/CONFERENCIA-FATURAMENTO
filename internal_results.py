"""Saídas internas: planilha somente de pendências, sem pacote para cliente."""
import io,json
import pandas as pd
import xlsxwriter
from reports import GOOD,safe_cell
from datetime import datetime,timezone


def pending_rows(rows):
    actions={
      'Não localizado':('Documento/nome não localizado','Buscar a relação correta ou localizar o colaborador antes de confirmar ausência.'),
      'Ausência confirmada':('Documento faltante confirmado','Obter o documento/relação faltante.'),
      'Documento ausente ou sem relação legível':('Arquivo ausente ou relação não reconhecida','Carregar o arquivo correto ou revisar o layout/leitura.'),
      'Revisar':('Identificação ainda não validada','Conferir a sugestão e a fonte; não afirmar ausência apenas pela divergência.'),
      'Conflito CPF':('CPF divergente','Apurar a identidade/CPF na fonte.'),
      'Competência divergente':('Mês incompatível','Buscar o documento da competência correta.'),
      'Leitura inconclusiva':('Leitura insuficiente','Revisar a imagem e localizar o nome/documento.')}
    selected=[]
    for row in rows:
        if not row.get('Obrigatório') or row['Status'] in GOOD:continue
        kind,action=actions.get(row['Status'],('Pendência a revisar','Conferir a documentação.'))
        selected.append({**row,'Tipo de pendência':kind,'Próxima ação':action})
    return sorted(selected,key=lambda r:(r['Colaborador'],r['Benefício'],r['Competência']))


def pending_workbook(rows,meta=None):
    selected=pending_rows(rows);buf=io.BytesIO();book=xlsxwriter.Workbook(buf,{'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False})
    head=book.add_format({'bold':True,'bg_color':'#092E65','font_color':'#FFFFFF','text_wrap':True});body=book.add_format({'font_color':'#153358','valign':'top','text_wrap':True});cpf=book.add_format({'num_format':'@','font_color':'#153358'});alert=book.add_format({'bg_color':'#FFF0CC','font_color':'#153358','text_wrap':True})
    def sheet(name,data):
        ws=book.add_worksheet(name);ws.hide_gridlines(2);ws.freeze_panes(1,0);ws.set_row(0,30)
        data=pd.DataFrame(data)
        if data.empty:ws.write_string(0,0,'Nenhuma pendência no escopo selecionado.',body);ws.set_column(0,0,70);return
        for col,key in enumerate(data.columns):ws.write_string(0,col,str(key),head);ws.set_column(col,col,min(65,max(17,len(str(key))+2)),cpf if 'CPF' in str(key) else body)
        for ri,values in enumerate(data.itertuples(index=False,name=None),1):
            for ci,value in enumerate(values):
                value=safe_cell(value)
                if isinstance(value,(int,float)) and not isinstance(value,bool):ws.write_number(ri,ci,value,body)
                else:ws.write_string(ri,ci,str(value),alert if data.columns[ci]=='Status' else cpf if 'CPF' in str(data.columns[ci]) else body)
        ws.autofilter(0,0,len(data),len(data.columns)-1)
    cols=['Colaborador','CPF','Empresa','Contrato','Competência','Benefício','Status','Tipo de pendência','Próxima ação','Nome documento','Centro de custo documento','VA zerado','Arquivo','Página','Observação','Revisor','Decisão em']
    detail=[{col:row.get(col,'') for col in cols} for row in selected]
    counts={}
    for row in selected:counts[(row['Benefício'],row['Status'])]=counts.get((row['Benefício'],row['Status']),0)+1
    sheet('Resumo',[{'Benefício':b,'Status':s,'Quantidade de pendências':n} for (b,s),n in sorted(counts.items())] or [{'Situação':'Nenhuma pendência','Quantidade de pendências':0}])
    sheet('Pendências',detail)
    sheet('Metadados',[{'Campo':k,'Valor':v} for k,v in (meta or {}).items()]+[{'Campo':'Gerado UTC','Valor':datetime.now(timezone.utc).isoformat()},{'Campo':'Uso','Valor':'Conferência interna para localizar documentos; não é relatório para cliente ou autorização de faturamento.'},{'Campo':'Regra','Valor':'Inclui somente exigências ainda pendentes, inclusive ausência confirmada. VA zerado confirmado não é pendência.'}])
    book.close();return buf.getvalue()
