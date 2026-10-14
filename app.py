from __future__ import annotations
import io, os, json, hashlib, time, copy
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import streamlit as st
import pandas as pd
import altair as alt
import pymupdf as fitz
from engine import *
from reports import matrix,GOOD
from internal_results import pending_workbook
from pdf_highlights import marked_pdf_zip,FINISHED
from point_ui import render_point_workspace
from ui_theme import THEME_CSS

st.set_page_config(page_title='Lider Limpe | Conferência',page_icon='assets/logo.png',layout='wide',initial_sidebar_state='expanded')
st.markdown(THEME_CSS,unsafe_allow_html=True)


st.markdown('<div class="hero"><h1>Conferência inteligente</h1><p>Lider Limpe · Documentos, benefícios e ponto em uma única central auditável.</p></div>',unsafe_allow_html=True)
with st.sidebar:
    st.image('assets/logo.png',width=88)
    st.title('Lider Limpe')
    st.caption('CENTRAL DE CONFERÊNCIA')
    st.session_state['user']=st.text_input('Nome do conferente (opcional)',value=st.session_state.get('user','Conferente'),key='reviewer_name',help='Somente para identificar as revisões. Não é login e não exige senha.').strip() or 'Não identificado (sem login)'
    st.caption('Acesso sem senha. O nome do conferente é declarado, não autenticado. Restrinja o acesso na hospedagem.')
    st.info('CPF → nome exato → proximidade conservadora → revisão humana')
    if st.button('Encerrar e limpar sessão'):
        st.session_state.clear();st.rerun()
    st.caption('Sem API externa. PDFs e OCR são processados no servidor da hospedagem, não no navegador. Dados ficam na sessão; exporte a revisão para continuar depois.')


def now():return datetime.now(timezone.utc).isoformat()

def preview(file,page):
    blobs=st.session_state.get('blobs',{})
    if file not in blobs:st.warning('Arquivo não disponível na sessão.');return
    try:
        with fitz.open(stream=blobs[file],filetype='pdf') as d:
            if not 1<=int(page)<=len(d):st.warning('Página inválida.');return
            pix=d[int(page)-1].get_pixmap(dpi=110)
            st.image(pix.tobytes('png'),caption=f'{file} · página {page}',width='stretch')
    except Exception as exc:st.error(f'Não foi possível visualizar: {exc}')


def save_decision(row_id,action,record_id='',note=''):
    previous=st.session_state.setdefault('decisions',{}).get(row_id)
    decision={'action':action,'record_id':record_id,'note':note,'reviewer':st.session_state.user,'at':now()}
    st.session_state.decisions[row_id]=decision
    st.session_state.setdefault('decision_history',[]).append({'conferencia_id':row_id,'anterior':previous,'nova':decision})
    st.session_state.pop('result_signature',None)


tabs=st.tabs(['01 · Documentos','02 · Painel','03 · Revisão','04 · Auditoria','05 · Resultados internos'])
with tabs[0]:
    st.subheader('Um lote por conferência, com múltiplas folhas')
    st.caption('Carregue PDFs ou ZIPs. Confira a categoria antes de processar. Arquivos financeiros não são usados como lista de colaboradores.')
    uploaded=st.file_uploader('Folhas, relações de benefícios e folhas de ponto',type=['pdf','zip'],accept_multiple_files=True,key='uploads')
    files=[];msgs=[]
    if uploaded:
        try:files,msgs=unpack_files([(f.name,f.getvalue()) for f in uploaded],keep_duplicates=True)
        except Exception as exc:st.error(str(exc))
    for msg in msgs:st.caption(msg)
    categories={};declared_months={}
    if files:
        st.write(f'**{len(files)} PDFs únicos** · {sum(len(b) for _,b,_ in files)/1024/1024:.1f} MB')
        mapped=[]
        for name,data,h in files:
            with fitz.open(stream=data,filetype='pdf') as d:sample=d[0].get_text() if not d.needs_pass and len(d) else ''
            mapped.append({'Arquivo':name,'Categoria':classify_file(name,sample),'Competência informada':month_hint(name),'SHA256':h})
        editor=st.data_editor(pd.DataFrame(mapped)[['Arquivo','Categoria','Competência informada']],hide_index=True,width='stretch',disabled=['Arquivo'],column_config={'Categoria':st.column_config.SelectboxColumn(options=['Folha']+BENEFITS+['Não classificado'],required=True),'Competência informada':st.column_config.TextColumn(help='MM/AAAA. Sugestão pelo nome do arquivo; confirme o mês de referência. A folha usa o mês reconhecido no próprio PDF.')},key='file_map')
        categories=dict(zip(editor.Arquivo,editor.Categoria))
        declared_months={str(row['Arquivo']):str(row['Competência informada']).strip() if pd.notna(row['Competência informada']) else '' for row in editor.to_dict('records')}
        st.caption('Confira a competência informada de cada relação. A sugestão vem do nome do arquivo, não da data do pagamento. Ex.: crédito pago em junho pode pertencer à conferência de julho. A folha usa o mês identificado no PDF.')
    c1,c2,c3=st.columns(3)
    use_ocr=c1.checkbox('OCR em páginas escaneadas',True)
    include_point=c2.checkbox('Conferir presença da folha de ponto',True)
    dpi=c3.selectbox('Qualidade do OCR',[180,220,260],help='Mais resolução aumenta o tempo e a memória. Manuscritos continuam sujeitos a revisão.')
    vt_mode=st.selectbox('Regra do VT para guarda-vidas',['Qualquer operadora','Ambas para guarda-vidas'],help='Qualquer operadora: o crédito positivo pode constar em GVBUS OU Alvorada. Ambas: exige os dois relatórios para cargos com GUARDA e VIDA. Demais cargos: somente GVBUS.')
    st.caption('Todos da folha: VA, saúde, odonto, seguro e Idesbre. Sindicato: rubrica Sindilimpe de desconto. VT: rubrica VALE TRANSPORTE de desconto. Dispensas precisam de justificativa manual.')
    current_fingerprint=uid(*sorted(h+categories.get(n,'')+declared_months.get(n,'') for n,_,h in files),use_ocr,dpi,include_point,vt_mode) if files else ''
    if st.session_state.get('batch') and current_fingerprint and st.session_state.batch!=current_fingerprint:st.warning('Os arquivos/configurações mudaram. O resultado exibido ainda pertence ao lote anterior. Clique em Processar para atualizar.')
    if st.button('Processar conferência',type='primary',disabled=not files):
        if 'Folha' not in categories.values():st.error('Classifique pelo menos um PDF como Folha.')
        elif 'Não classificado' in categories.values():st.error('Classifique todos os PDFs; não há descarte silencioso.')
        elif any(value and not re.fullmatch(r'(0[1-9]|1[0-2])/20\d{2}',value) for value in declared_months.values()):st.error('Competência informada inválida. Use MM/AAAA, por exemplo 08/2026.')
        else:
            progress=st.progress(0);label=st.empty();all_pages=[];people=[];records=[];errors=[];payroll_pages=[];docs=[]
            blobs={n:b for n,b,_ in files};total=len(files)
            for index,(name,data,h) in enumerate(files):
                def cb(page,count,filename):
                    progress.progress(min(1.,(index+(page/count))/total));label.text(f'{filename} · página {page}/{count}')
                try:
                    pages=extract_pdf(name,data,h,ocr=use_ocr,dpi=dpi,progress=cb,focus=categories[name])
                    if categories[name]=='Folha':
                        parsed=payroll(pages);people+=parsed;payroll_pages+=pages
                        if not parsed:errors.append(f'{name}: nenhuma pessoa extraída da folha. Conferência incompleta.')
                    else:docs.append((name,pages,categories[name]))
                    all_pages+=pages
                except Exception as exc:errors.append(f'{name}: {exc}')
            # Deduplicação entre diferentes PDFs da folha, sem misturar empresa/contrato/competência.
            grouped={}
            for e in people:
                if e.id not in grouped:grouped[e.id]=e
                else:
                    old=grouped[e.id];old.sources+=e.sources
                    if norm(old.name)!=norm(e.name) or old.vt!=e.vt or old.union!=e.union:old.warnings.append('Folhas sobrepostas com divergências: revisar.')
                    old.vt|=e.vt;old.union|=e.union
            people=list(grouped.values());known_cnpj={e.cnpj for e in people if e.cnpj}
            for name,pages,kind in docs:
                text='\n'.join(p.text for p in pages[:5]);owners=[c for c in known_cnpj if c in text or re.sub(r'\D','',c) in text]
                rr=parse_records(pages,kind)
                try:assign_document_month(pages,rr,declared_months.get(name,''))
                except ValueError as exc:errors.append(f'{name}: {exc}')
                if kind=='VT Alvorada' and not any(r.competence for r in rr):errors.append(f'{name}: informe a competência desta relação Alvorada na tabela de arquivos. Não é usada a data de pagamento como mês da folha.')
                if len(owners)==1:
                    for r in rr:r.company_cnpj=owners[0]
                elif len(known_cnpj)>1:errors.append(f'{name}: empresa não determinada de forma única. Separar o lote por empresa ou revisar antes da entrega.')
                records+=rr
            if not people:st.error('Nenhum colaborador reconhecido. Revise o layout da folha. Não há resultado confiável.')
            else:
                st.session_state.update({'people':people,'records':records,'pages':all_pages,'blobs':blobs,'batch':current_fingerprint,'decisions':{},'errors':errors,'messages':msgs,'base_audit':[],'config':{'ponto':include_point,'vt_mode':vt_mode,'dpi':dpi,'ocr':use_ocr,'categorias':categories,'competencias_documentos':declared_months},'manifest':{n:h for n,_,h in files},'manual_records':[],'decision_history':[],'point_areas':{},'app_version':'3.0'})
                st.session_state.pop('result_signature',None)
                st.success(f'Leitura concluída: {len(people)} colaboradores e {len(all_pages)} páginas examinadas. Consulte pendências e auditoria.')
                label.empty();progress.empty()
    if st.session_state.get('errors'):
        for error in st.session_state.errors:st.error(error)

if 'people' not in st.session_state:
    with tabs[1]:st.info('Carregue os documentos e processe o lote para visualizar o painel.')
    with tabs[2]:st.info('As correspondências incertas aparecerão aqui.')
    with tabs[3]:st.info('A auditoria mostrará cada página, incluindo as ignoradas como boleto/comprovante.')
    with tabs[4]:st.info('Ao concluir, exporte a planilha de pendências, salve a revisão e baixe os PDFs originais com marca-texto.')
    st.stop()

people=st.session_state.people;records=st.session_state.records;pages=st.session_state.pages
with st.sidebar:
    scope_options=sorted({(e.cnpj,e.contract,e.competence) for e in people})
    selected=st.multiselect('Escopo da conferência',scope_options,default=scope_options,format_func=lambda x:f'{x[1]} · {x[2]} · {x[0]}',key='scope')
scoped=[e for e in people if (e.cnpj,e.contract,e.competence) in selected]
if not scoped:
    st.warning('Selecione pelo menos um contrato no escopo.');st.stop()
# Mudanças de escopo/revisão invalidam somente a conferência; o OCR não é executado novamente.
signature=uid(st.session_state.batch,json.dumps(selected),json.dumps(st.session_state.decisions,sort_keys=True),len(records),json.dumps(st.session_state.get('base_audit',[]),sort_keys=True))
if signature!=st.session_state.get('result_signature'):
    with st.spinner('Comparando identidades e regras do escopo selecionado…'):
        rows,candidates,outside=reconcile(scoped,records,pages,vt_mode=st.session_state.config['vt_mode'],include_ponto=st.session_state.config['ponto'],decisions=st.session_state.decisions)
    st.session_state.update({'rows':rows,'candidates':candidates,'outside':outside,'result_signature':signature})
rows=st.session_state.rows;candidates=st.session_state.candidates;df=pd.DataFrame(rows)
pending=df[df.Obrigatório & ~df.Status.isin(GOOD)].copy();confirmed=df[df.Obrigatório & df.Status.isin(GOOD)]

with tabs[1]:
    a,b,c,d=st.columns(4)
    a.metric('Colaboradores na base',len(scoped));b.metric('Conferências exigidas',int(df.Obrigatório.sum()));c.metric('Confirmadas / dispensadas',len(confirmed));d.metric('Pendências',len(pending))
    ratio=len(confirmed)/max(int(df.Obrigatório.sum()),1);st.progress(ratio,text=f'{ratio:.0%} das exigências com conclusão documental')
    if pending.empty and not st.session_state.errors:st.success('Sem pendências no escopo conferido. Ainda é necessária a aprovação de entrega; a conferência não substitui validação fiscal.')
    else:st.warning('Resultado com pendências ou problemas de leitura. Não é liberação automática de faturamento.')
    left,right=st.columns([2,1])
    with left:
        st.subheader('Matriz por colaborador');search=st.text_input('Buscar colaborador',key='search_main')
        mat=matrix(rows);view=mat[mat.Colaborador.str.contains(search,case=False,regex=False)] if search else mat
        if len(selected)==1:view=view.drop(columns=['Empresa','Contrato','Competência','CPF'],errors='ignore')
        def color_status(value):
            return 'color: #153358; background-color: '+{'Confirmado':'#ddf2e5','Validado manualmente':'#dcecff','Revisar':'#fff1ca','Conflito CPF':'#fbdcdd','Não localizado':'#fbdcdd','Não exigido':'#edf0f5','Leitura inconclusiva':'#fff1ca','Dispensa justificada':'#eee7fa'}.get(str(value).split(' · ')[0],'white')
        st.dataframe(view.style.map(color_status),hide_index=True,width='stretch',height=440,column_config={'Colaborador':st.column_config.TextColumn(width='medium')})
    with right:
        st.subheader('Situação por benefício')
        counts=df[df.Obrigatório].groupby(['Benefício','Status']).size().unstack(fill_value=0)
        chart_data=counts.reset_index().melt(id_vars='Benefício',var_name='Status',value_name='Quantidade')
        chart=alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('Benefício:N',title=None,axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Quantidade:Q',title='Conferências'),
            color=alt.Color('Status:N',scale=alt.Scale(domain=['Confirmado','Validado manualmente','Revisar','Conflito CPF','Não localizado','Ausência confirmada','Documento ausente ou sem relação legível','Competência divergente','Leitura inconclusiva','Dispensa justificada'],range=['#08744C','#07559E','#A04B00','#B3261E','#9D3547','#8E253C','#6B526E','#6B4C9A','#806100','#66508D']),legend=alt.Legend(title='Situação')),
            tooltip=['Benefício:N','Status:N','Quantidade:Q']
        ).properties(height=410,background='#FFFFFF').configure_axis(labelColor='#153358',titleColor='#153358',gridColor='#CCD6E5',domainColor='#A9BAD1').configure_legend(labelColor='#153358',titleColor='#153358').configure_view(stroke='#CCD6E5')
        st.altair_chart(chart,theme=None,width='stretch')
    st.subheader('Cadastro reconhecido da folha')
    st.caption('Revise a base antes de aceitar o resultado. Situação trabalhista não dispensa automaticamente nenhum benefício.')
    base=pd.DataFrame([{'id':e.id,'Nome':e.name,'CPF':e.cpf,'Cargo':e.job,'VT obrigatório':e.vt,'Sindicato obrigatório':e.union,'Empresa':e.company,'Contrato':e.contract,'Competência':e.competence,'Alertas':' | '.join(e.warnings)} for e in scoped])
    with st.expander('Corrigir rubricas e validar alertas da base'):
        edit=st.data_editor(base.drop(columns=['id']),disabled=['Nome','CPF','Cargo','Empresa','Contrato','Competência','Alertas'],hide_index=True,width='stretch',key='edit_base')
        note=st.text_input('Justificativa da alteração/validação da base',key='note_base')
        validated=st.checkbox('Conferi visualmente os cadastros e rubricas deste escopo',key='base_validated')
        if st.button('Salvar ajustes da base'):
            if not note.strip():st.error('Informe uma justificativa.')
            else:
                for idx,e in enumerate(scoped):
                    old=(e.vt,e.union,list(e.warnings));e.vt=bool(edit.iloc[idx]['VT obrigatório']);e.union=bool(edit.iloc[idx]['Sindicato obrigatório'])
                    if validated:e.warnings=[]
                    if old!=(e.vt,e.union,e.warnings):st.session_state.base_audit.append({'id':e.id,'antes':old,'depois':[e.vt,e.union,e.warnings],'revisor':st.session_state.user,'nota':note,'em':now()})
                st.rerun()

with tabs[2]:
    st.subheader('Revisão assistida · nenhuma dúvida vira confirmação silenciosa')
    st.caption('Similaridade é um índice textual, não uma probabilidade. Abreviações, OCR, homônimos e conflito de CPF exigem decisão humana.')
    filterbenefit=st.selectbox('Benefício para revisar',['Todos']+sorted(df.Benefício.unique().tolist()),key='review_kind')
    show_all=st.checkbox('Incluir conferências já concluídas',False)
    view=df[df.Obrigatório].copy() if show_all else pending.copy()
    if filterbenefit!='Todos':view=view[view.Benefício==filterbenefit]
    if not view.empty:
        byrow={r['id']:r for r in view.to_dict('records')}
        rid=st.selectbox('Conferência',list(byrow),format_func=lambda k:f"{byrow[k]['Colaborador']} · {byrow[k]['Benefício']} · {byrow[k]['Status']}",key='review_row')
        row=byrow[rid];e=next(x for x in scoped if x.id==row['colaborador_id']);is_guard='GUARDA' in norm(e.job) and 'VIDA' in norm(e.job);kinds=(['VT GVBUS','VT Alvorada'] if is_guard else ['VT GVBUS']) if row['Benefício']=='VT' else [row['Benefício']]
        suggestions=candidates.get(rid,[])
        if suggestions:st.dataframe(pd.DataFrame(suggestions).drop(columns=['id','evidencia']).style.set_properties(**{'color':'#153358','background-color':'#FFFFFF'}),hide_index=True,width='stretch')
        left,right=st.columns(2)
        with left:
            st.markdown(f'**Na folha:** {e.name}');st.write(f'CPF: {e.cpf} · cargo: {e.job}')
            with st.expander('Trecho extraído da folha'):st.text(e.evidence)
            if st.checkbox('Visualizar página da folha',key='preview_payroll'):preview(e.file,e.page)
        with right:
            query=st.text_input('Buscar outro nome/CPF na documentação',key='review_query')
            pool=[r for r in records if r.benefit in kinds and (not r.company_cnpj or r.company_cnpj==e.cnpj)]
            if query:
                pool=[r for r in pool if norm(query) in norm(r.name) or (re.sub(r'\D','',query) and re.sub(r'\D','',query) in r.cpf)]
            else:
                ids={x['id'] for x in suggestions};pool=[r for r in pool if r.id in ids]
                pool.sort(key=lambda r:next((i for i,x in enumerate(suggestions) if x['id']==r.id),999))
            pool=pool[:200]
            choices={'':None,**{r.id:r for r in pool}}
            record_id=st.selectbox('Registro documental',list(choices),format_func=lambda k:'Sem registro selecionado' if not k else f'{choices[k].name} · CPF {choices[k].cpf or "não informado"} · p.{choices[k].page}'+(' · INATIVO/ZERO' if not choices[k].active else ''),key=f'doc_{rid}')
            rec=choices[record_id]
            if rec:
                st.text(rec.evidence)
                if rec.warnings:st.warning(' | '.join(rec.warnings))
                if st.checkbox('Visualizar documento selecionado',value=True,key='preview_doc'):preview(rec.file,rec.page)
        with st.form('individual_review'):
            action=st.selectbox('Decisão',['Vincular ao registro selecionado','Confirmar ausência após conferência visual','Dispensar com justificativa','Remover decisão anterior'])
            note=st.text_area('Justificativa / evidência da revisão',help='Obrigatória. Registre como verificou a identidade ou a ausência.')
            agree=st.checkbox('Conferi a evidência e assumo a decisão registrada')
            if st.form_submit_button('Registrar decisão',type='primary'):
                if not agree or not note.strip():st.error('Confirmação e justificativa são obrigatórias.')
                elif action=='Vincular ao registro selecionado' and not rec:st.error('Selecione um registro documental.')
                elif action=='Vincular ao registro selecionado' and (not rec.active or (rec.competence and rec.competence!=e.competence)):st.error('Registro inativo (ou VT zerado) ou de outra competência não confirma concessão. Use documentação correta ou dispensa justificada.')
                elif action=='Remover decisão anterior':save_decision(rid,'clear','',note);st.rerun()
                else:
                    save_decision(rid,{'Vincular ao registro selecionado':'confirm','Confirmar ausência após conferência visual':'missing','Dispensar com justificativa':'waive'}[action],record_id,note);st.rerun()
        with st.expander('Validação em lote das sugestões — somente após revisão'):
            bulk=[]
            for r in view.to_dict('records'):
                cs=candidates.get(r['id'],[])
                if cs and r['Status'] not in ['Conflito CPF'] and cs[0]['score']>=80:
                    rr=next((x for x in records if x.id==cs[0]['id']),None)
                    if rr and rr.active and not rr.ocr and not (rr.cpf and (not cpf_valid(rr.cpf) or rr.cpf!=r['CPF'])):
                        bulk.append({'Selecionar':False,'id':r['id'],'registro_id':rr.id,'Colaborador folha':r['Colaborador'],'Nome documentação':rr.name,'Similaridade':cs[0]['score'],'Benefício':r['Benefício']})
            if bulk:
                all_bulk=st.checkbox('Selecionar todas as sugestões elegíveis',False)
                table=pd.DataFrame(bulk);table['Selecionar']=all_bulk
                edited=st.data_editor(table.drop(columns=['id','registro_id']),disabled=['Colaborador folha','Nome documentação','Similaridade','Benefício'],hide_index=True,key='bulk_editor')
                bulk_note=st.text_input('Justificativa da revisão em lote',key='bulk_note');bulk_agree=st.checkbox('Comparei todos os pares selecionados',key='bulk_agree')
                if st.button('Confirmar os pares selecionados'):
                    if not bulk_agree or not bulk_note.strip():st.error('Confirme a revisão e informe a justificativa.')
                    else:
                        for i,entry in enumerate(bulk):
                            if edited.iloc[i]['Selecionar']:save_decision(entry['id'],'confirm',entry['registro_id'],bulk_note)
                        st.rerun()
            else:st.info('Não há pares elegíveis para validação em lote. Conflitos de CPF e OCR exigem revisão individual.')
    else:st.success('Nenhuma conferência neste filtro.')
    with st.expander('Ponto escaneado: identificar visualmente uma página',expanded=False):
        render_point_workspace(scoped,pages,records,rows,preview,save_decision)

with tabs[3]:
    st.subheader('Rastreabilidade de todas as páginas')
    audit=pd.DataFrame([{'Arquivo':p.file,'Página':p.number,'Classificação':p.layout,'Registros':p.records,'OCR':p.ocr,'Confiança OCR':p.confidence,'Erro':p.error,'Competência':p.competence} for p in pages])
    st.dataframe(audit.style.set_properties(**{'color':'#153358','background-color':'#FFFFFF'}),hide_index=True,width='stretch',height=420)
    problem=audit[(audit.Erro!='')|audit.Classificação.str.contains('nenhum|inconclusiva|não identificado',case=False)]
    if not problem.empty:st.warning(f'{len(problem)} páginas requerem atenção; ausência de leitura não confirma falta de colaborador.')
    st.caption('Páginas financeiras ficam separadas das relações. Confiança do OCR é uma métrica do reconhecedor, não garantia de identificação correta.')
    with st.expander('Texto extraído e inspeção de uma página'):
        pindex=st.selectbox('Arquivo/página',range(len(pages)),format_func=lambda i:f'{pages[i].file} · p.{pages[i].number}',key='audit_page')
        p=pages[pindex];st.text_area('Texto',p.text,height=300,disabled=True)
        if st.checkbox('Abrir imagem da página',key='audit_preview'):preview(p.file,p.number)
    with st.expander('Registros sem vínculo na base selecionada — informativo'):
        st.caption('Relações podem abranger toda a empresa. Pessoas de outros contratos não são divergência deste contrato. Esta lista não vai ao pacote do cliente.')
        st.dataframe(pd.DataFrame(st.session_state.outside).drop(columns=['evidence'],errors='ignore').style.set_properties(**{'color':'#153358','background-color':'#FFFFFF'}),hide_index=True,width='stretch')
    with st.expander('Registro de decisões humanas'):
        st.json(st.session_state.decisions);st.json(st.session_state.base_audit);st.json(st.session_state.get('decision_history',[]))

with tabs[4]:
    st.subheader('Resultados internos · pendências e PDFs com marca-texto')
    st.caption('Não há relatório/pacote de resultado para cliente. Estas saídas ajudam a localizar documentos e conferir internamente.')
    meta={'Escopo':' | '.join(f'{x[1]} / {x[2]} / {x[0]}' for x in selected),'Revisor':st.session_state.user,'Lote':st.session_state.batch,'Pendências':len(pending),'Uso':'Somente interno'}
    if st.button('Gerar planilha de pendências',type='primary'):
        st.session_state['pending_export']=(signature,pending_workbook(rows,meta))
    if st.session_state.get('pending_export',('',))[0]==signature:
        st.download_button('Baixar Excel somente com pendências',st.session_state.pending_export[1],'lider_limpe_pendencias.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption('A planilha inclui não localizados, ausência confirmada, nomes/CPF a revisar, mês incompatível e leitura inconclusiva. Não inclui confirmados, dispensados ou não exigidos.')
    checkpoint={'schema':1,'manifest':st.session_state.manifest,'config':st.session_state.config,'decisions':st.session_state.decisions,'manual_records':st.session_state.manual_records,'base':[{'id':e.id,'vt':e.vt,'union':e.union,'warnings':e.warnings} for e in people],'base_audit':st.session_state.base_audit,'decision_history':st.session_state.get('decision_history',[]),'point_areas':st.session_state.get('point_areas',{}),'version':'3.0','saved_at':now()}
    st.download_button('Salvar revisão para continuar depois (JSON interno)',json.dumps(checkpoint,ensure_ascii=False,indent=2).encode(),'lider_limpe_revisao_interna.json','application/json')
    imported=st.file_uploader('Restaurar revisão do mesmo lote',type=['json'],key='checkpoint')
    if imported and st.button('Aplicar revisão salva'):
        try:
            if imported.size>8*1024*1024:raise ValueError('Arquivo excede 8 MB.')
            cp=json.loads(imported.getvalue())
            if cp.get('schema')!=1 or cp.get('manifest')!=st.session_state.manifest or any(st.session_state.config.get(k)!=v for k,v in cp.get('config',{}).items()):raise ValueError('Outro lote/configuração. Recarregue os mesmos PDFs/opções.')
            knownpages={(p.file,p.number) for p in pages};restored=[]
            for raw in cp.get('manual_records',[]):
                r=Record(**raw)
                if (r.file,r.page) not in knownpages or r.benefit!='Ponto':raise ValueError('Registro manual incompatível com o lote.')
                restored.append(r)
            validids={r.id for r in records+restored}
            if any(d.get('action') not in ['confirm','waive','missing','clear'] or (d.get('action')=='confirm' and d.get('record_id') not in validids) for d in cp.get('decisions',{}).values()):raise ValueError('Vínculos incompatíveis: a extração por colunas desta versão mudou. Revise o lote novamente; não será feita migração automática de nomes.')
            for r in restored:
                if r.id not in {x.id for x in records}:records.append(r)
            st.session_state.manual_records=[asdict(r) for r in restored];st.session_state.decisions=cp.get('decisions',{})
            overrides={e['id']:e for e in cp.get('base',[])}
            for e in people:
                if e.id in overrides:e.vt=bool(overrides[e.id]['vt']);e.union=bool(overrides[e.id]['union']);e.warnings=list(overrides[e.id]['warnings'])
            st.session_state.base_audit=cp.get('base_audit',[]);st.session_state.decision_history=cp.get('decision_history',[]);st.session_state.point_areas=cp.get('point_areas',{});st.rerun()
        except Exception as exc:st.error(f'Revisão não aplicada: {exc}')
    st.divider()
    unresolved=df[df.Obrigatório & ~df.Status.isin(FINISHED)]
    st.subheader('PDFs originais com marca-texto · baixar somente ao terminar')
    st.write(f'Conferências ainda sem conclusão: **{len(unresolved)}**')
    st.caption('Marca nomes com vínculo Confirmado/Validado manualmente e exigência ativa. VA zerado confirmado pode ser marcado; VT/Sindicato somente se exigidos pela folha. Ausência confirmada encerra a revisão, mas continua na planilha de pendências. Não marca sugestões ou dispensas.')
    st.caption('Mantém os nomes dos PDFs, todas as páginas e a ordem original, inclusive boletos e comprovantes. A origem não é sobrescrita. Arquivos homônimos ficam em subpastas. Marcas são anotações editáveis; alterações invalidam eventuais assinaturas digitais do PDF.')
    if st.session_state.errors:st.error('Há erros de processamento: corrija/reprocesse antes do ZIP final.')
    if len(unresolved):st.info('Resolva os vínculos incertos ou confirme a ausência após conferir. O ZIP final fica bloqueado enquanto houver revisão em aberto.')
    if st.button('Preparar ZIP dos PDFs com marca-texto',type='primary',disabled=bool(len(unresolved)) or bool(st.session_state.errors)):
        bar=st.progress(0);label=st.empty()
        try:
            def markprogress(current,total,filename):bar.progress(current/max(total,1));label.text(filename)
            blob,log=marked_pdf_zip(st.session_state.blobs,scoped,records,pages,rows,markprogress)
            st.session_state['pdf_export']=(signature,blob,log)
        except Exception as exc:st.error(f'PDFs não preparados: {exc}')
        finally:bar.empty();label.empty()
    if st.session_state.get('pdf_export',('',))[0]==signature and not len(unresolved) and not st.session_state.errors:
        export=st.session_state.pdf_export;log=export[2]
        misses=[line for line in log if line[4]=='SEM MARCAÇÃO']
        if misses:st.warning(f'{len(misses)} nomes vinculados ainda não têm área segura de marcação. O download fica bloqueado para não entregar um ZIP incompleto. Em ponto manuscrito, indique a área do nome na mesa de ponto e prepare o ZIP novamente.')
        if log:
            with st.expander('Controle de marcações / nomes sem área identificada'):
                st.dataframe(pd.DataFrame(log,columns=['Arquivo','Página','Nome na relação','Nome da folha','Resultado','Localização']).style.set_properties(**{'color':'#153358','background-color':'#FFFFFF'}),hide_index=True,width='stretch')
        st.download_button('Baixar ZIP dos PDFs originais marcados',export[1],'lider_limpe_pdfs_marcados.zip','application/zip',disabled=bool(misses))
    st.warning('Planilha, JSON e PDFs contêm dados pessoais. Uso interno; não publique no GitHub.')
