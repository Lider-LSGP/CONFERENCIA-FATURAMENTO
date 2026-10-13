from __future__ import annotations
import io, os, json, hashlib, time, copy
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import streamlit as st
import pandas as pd
import pymupdf as fitz
from engine import *
from reports import workbook,matrix,client_package,GOOD
from security import verify_password

st.set_page_config(page_title='Lider Limpe | Conferência',page_icon='assets/logo.png',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp{background:#f4f7fb}section[data-testid="stSidebar"]{background:#092e65}section[data-testid="stSidebar"] *{color:#f4f7fb}section[data-testid="stSidebar"] input{color:#16335b!important}.block-container{padding-top:1.7rem;max-width:1580px}h1,h2,h3{color:#0a3067}div[data-testid="stMetric"]{background:white;border:1px solid #e4eaf3;border-radius:16px;padding:18px;border-top:4px solid #f47a00}div[data-testid="stTabs"] button{font-weight:600}.hero{background:linear-gradient(120deg,#05275c,#104782);color:white;padding:27px 32px;border-radius:22px;margin-bottom:22px}.hero h1{color:white!important;font-size:2.05rem;margin:0}.hero p{color:#dbe7f8;margin:8px 0 0}.step{background:white;border:1px solid #e1e8f3;border-radius:15px;padding:16px;margin-bottom:12px}.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{background:#f47a00;border:0;color:white;border-radius:10px}section[data-testid="stSidebar"] .stButton>button{background:#16437b;color:white;border:1px solid #45668e}section[data-testid="stSidebar"] .stButton>button *{color:white!important}footer{visibility:hidden}
</style>''',unsafe_allow_html=True)


def auth():
    try: users=dict(st.secrets.get('auth',{}).get('users',{}))
    except Exception:users={}
    if os.environ.get('LIDER_LOCAL_DEV')=='1':
        st.warning('Modo local de desenvolvimento: sem autenticação. Não utilizar em publicação.');st.session_state['user']='desenvolvimento';return
    if st.session_state.get('user'):return
    if not users:
        st.error('Acesso bloqueado: configure [auth.users] nos Secrets antes de usar documentos pessoais.')
        st.code('[auth.users]\nconferente = "HASH_GERADO_PELO_security.py"',language='toml')
        st.info('No computador: execute python security.py, copie o hash e configure .streamlit/secrets.toml. Na hospedagem, cole em Settings → Secrets. Não publique senhas ou documentos no GitHub.')
        st.stop()
    with st.form('login'):
        st.subheader('Área restrita · Lider Limpe')
        username=st.text_input('Usuário');password=st.text_input('Senha',type='password');submitted=st.form_submit_button('Entrar',type='primary')
    if submitted:
        now=time.monotonic();blocked=st.session_state.get('blocked_until',0)
        if now<blocked:st.error('Aguarde um minuto antes de tentar novamente.')
        elif verify_password(password,users.get(username,'')):
            st.session_state['user']=username;st.session_state['failures']=0;st.rerun()
        else:
            st.session_state['failures']=st.session_state.get('failures',0)+1
            if st.session_state['failures']>=5:st.session_state['blocked_until']=now+60;st.session_state['failures']=0
            st.error('Credenciais inválidas.')
    st.caption('Proteção básica do aplicativo. Para produção, usar também acesso privado/SSO e políticas de retenção do ambiente de hospedagem.')
    st.stop()

st.markdown('<div class="hero"><h1>Conferência inteligente</h1><p>Lider Limpe · Documentos, benefícios e ponto em uma única central auditável.</p></div>',unsafe_allow_html=True)
auth()
with st.sidebar:
    st.image('assets/logo.png',width=88)
    st.title('Lider Limpe')
    st.caption('CENTRAL DE CONFERÊNCIA')
    st.write(f'Conferente: {st.session_state.user}')
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
            st.image(pix.tobytes('png'),caption=f'{file} · página {page}',use_container_width=True)
    except Exception as exc:st.error(f'Não foi possível visualizar: {exc}')


def save_decision(row_id,action,record_id='',note=''):
    st.session_state.setdefault('decisions',{})[row_id]={'action':action,'record_id':record_id,'note':note,'reviewer':st.session_state.user,'at':now()}
    st.session_state.pop('result_signature',None)


tabs=st.tabs(['01 · Documentos','02 · Painel','03 · Revisão','04 · Auditoria','05 · Entrega'])
with tabs[0]:
    st.subheader('Um lote por conferência, com múltiplas folhas')
    st.caption('Carregue PDFs ou ZIPs. Confira a categoria antes de processar. Arquivos financeiros não são usados como lista de colaboradores.')
    uploaded=st.file_uploader('Folhas, relações de benefícios e folhas de ponto',type=['pdf','zip'],accept_multiple_files=True,key='uploads')
    files=[];msgs=[]
    if uploaded:
        try:files,msgs=unpack_files([(f.name,f.getvalue()) for f in uploaded])
        except Exception as exc:st.error(str(exc))
    for msg in msgs:st.caption(msg)
    categories={}
    if files:
        st.write(f'**{len(files)} PDFs únicos** · {sum(len(b) for _,b,_ in files)/1024/1024:.1f} MB')
        mapped=[]
        for name,data,h in files:
            with fitz.open(stream=data,filetype='pdf') as d:sample=d[0].get_text() if not d.needs_pass and len(d) else ''
            mapped.append({'Arquivo':name,'Categoria':classify_file(name,sample),'SHA256':h})
        editor=st.data_editor(pd.DataFrame(mapped)[['Arquivo','Categoria']],hide_index=True,use_container_width=True,disabled=['Arquivo'],column_config={'Categoria':st.column_config.SelectboxColumn(options=['Folha']+BENEFITS+['Não classificado'],required=True)},key='file_map')
        categories=dict(zip(editor.Arquivo,editor.Categoria))
    c1,c2,c3=st.columns(3)
    use_ocr=c1.checkbox('OCR em páginas escaneadas',True)
    include_point=c2.checkbox('Conferir presença da folha de ponto',True)
    dpi=c3.selectbox('Qualidade do OCR',[180,220,260],help='Mais resolução aumenta o tempo e a memória. Manuscritos continuam sujeitos a revisão.')
    vt_mode=st.selectbox('Regra do VT para guarda-vidas',['Qualquer operadora','Ambas para guarda-vidas'],help='Qualquer operadora: o crédito positivo pode constar em GVBUS OU Alvorada. Ambas: exige os dois relatórios para cargos com GUARDA e VIDA. Demais cargos: somente GVBUS.')
    st.caption('Todos da folha: VA, saúde, odonto, seguro e Idesbre. Sindicato: rubrica Sindilimpe de desconto. VT: rubrica VALE TRANSPORTE de desconto. Dispensas precisam de justificativa manual.')
    current_fingerprint=uid(*sorted(h+categories.get(n,'') for n,_,h in files),use_ocr,dpi,include_point,vt_mode) if files else ''
    if st.session_state.get('batch') and current_fingerprint and st.session_state.batch!=current_fingerprint:st.warning('Os arquivos/configurações mudaram. O resultado exibido ainda pertence ao lote anterior. Clique em Processar para atualizar.')
    if st.button('Processar conferência',type='primary',disabled=not files):
        if 'Folha' not in categories.values():st.error('Classifique pelo menos um PDF como Folha.')
        elif 'Não classificado' in categories.values():st.error('Classifique todos os PDFs; não há descarte silencioso.')
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
                if len(owners)==1:
                    for r in rr:r.company_cnpj=owners[0]
                elif len(known_cnpj)>1:errors.append(f'{name}: empresa não determinada de forma única. Separar o lote por empresa ou revisar antes da entrega.')
                records+=rr
            if not people:st.error('Nenhum colaborador reconhecido. Revise o layout da folha. Não há resultado confiável.')
            else:
                st.session_state.update({'people':people,'records':records,'pages':all_pages,'blobs':blobs,'batch':current_fingerprint,'decisions':{},'errors':errors,'messages':msgs,'base_audit':[],'config':{'ponto':include_point,'vt_mode':vt_mode,'dpi':dpi,'ocr':use_ocr},'manifest':{n:h for n,_,h in files},'manual_records':[]})
                st.session_state.pop('result_signature',None)
                st.success(f'Leitura concluída: {len(people)} colaboradores e {len(all_pages)} páginas examinadas. Consulte pendências e auditoria.')
                label.empty();progress.empty()
    if st.session_state.get('errors'):
        for error in st.session_state.errors:st.error(error)

if 'people' not in st.session_state:
    with tabs[1]:st.info('Carregue os documentos e processe o lote para visualizar o painel.')
    with tabs[2]:st.info('As correspondências incertas aparecerão aqui.')
    with tabs[3]:st.info('A auditoria mostrará cada página, incluindo as ignoradas como boleto/comprovante.')
    with tabs[4]:st.info('Ao concluir, exporte Excel interno, revisão recuperável e pacote específico para o cliente.')
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
            return 'background-color: '+{'Confirmado':'#ddf2e5','Validado manualmente':'#dcecff','Revisar':'#fff1ca','Conflito CPF':'#fbdcdd','Não localizado':'#fbdcdd','Não exigido':'#edf0f5','Leitura inconclusiva':'#fff1ca','Dispensa justificada':'#eee7fa'}.get(str(value),'white')
        st.dataframe(view.style.map(color_status),hide_index=True,use_container_width=True,height=440,column_config={'Colaborador':st.column_config.TextColumn(width='medium')})
    with right:
        st.subheader('Situação por benefício')
        counts=df[df.Obrigatório].groupby(['Benefício','Status']).size().unstack(fill_value=0)
        st.bar_chart(counts,height=410)
    st.subheader('Cadastro reconhecido da folha')
    st.caption('Revise a base antes de aceitar o resultado. Situação trabalhista não dispensa automaticamente nenhum benefício.')
    base=pd.DataFrame([{'id':e.id,'Nome':e.name,'CPF':e.cpf,'Cargo':e.job,'VT obrigatório':e.vt,'Sindicato obrigatório':e.union,'Empresa':e.company,'Contrato':e.contract,'Competência':e.competence,'Alertas':' | '.join(e.warnings)} for e in scoped])
    with st.expander('Corrigir rubricas e validar alertas da base'):
        edit=st.data_editor(base.drop(columns=['id']),disabled=['Nome','CPF','Cargo','Empresa','Contrato','Competência','Alertas'],hide_index=True,use_container_width=True,key='edit_base')
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
        if suggestions:st.dataframe(pd.DataFrame(suggestions).drop(columns=['id','evidencia']),hide_index=True,use_container_width=True)
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
                elif action=='Vincular ao registro selecionado' and (not rec.active or (rec.competence and rec.competence!=e.competence)):st.error('Registro inativo/zero ou de outra competência não confirma concessão. Use documentação correta ou dispensa justificada.')
                elif action=='Remover decisão anterior':st.session_state.decisions.pop(rid,None);st.rerun()
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
    with st.expander('Ponto escaneado: identificar visualmente uma página'):
        pointfiles={r.file for r in records if r.benefit=='Ponto'}|{p.file for p in pages if p.layout.startswith(('Folha de ponto','Ponto:'))}
        pointpages=[p for p in pages if p.file in pointfiles]
        if pointpages:
            opts={uid(p.file_hash,p.number):p for p in pointpages}
            pk=st.selectbox('Página de ponto',list(opts),format_func=lambda k:f'{opts[k].file} · p.{opts[k].number} · {opts[k].layout}',key='point_page')
            p=opts[pk];preview(p.file,p.number)
            pe=st.selectbox('Colaborador identificado visualmente',scoped,format_func=lambda x:x.name+' · '+x.contract,key='point_employee')
            pointnote=st.text_input('Evidência visual da identificação',key='point_note')
            if st.button('Vincular esta página ao colaborador'):
                if not pointnote.strip():st.error('Descreva a evidência visual.')
                elif p.competence and p.competence!=pe.competence:st.error('A competência desta folha de ponto difere da folha de pagamento selecionada.')
                else:
                    occupied=[r for r in records if r.benefit=='Ponto' and r.file==p.file and r.page==p.number and any(d.get('record_id')==r.id and d.get('action')=='confirm' for d in st.session_state.decisions.values())]
                    if occupied and any(norm(r.name)!=norm(pe.name) for r in occupied):st.error('Esta página já está vinculada a outro colaborador. Remova primeiro a decisão anterior.')
                    else:
                        r=Record(uid('manual',p.file_hash,p.number,pe.id),'Ponto',pe.name,pe.cpf,p.file,p.number,pointnote,True,100,True,p.competence or pe.competence,company_cnpj=pe.cnpj)
                        if r.id not in {x.id for x in records}:records.append(r);st.session_state.manual_records.append(asdict(r))
                        save_decision(uid(pe.id,'Ponto'),'confirm',r.id,pointnote);st.rerun()
        else:st.info('Nenhum PDF de ponto foi processado neste lote.')

with tabs[3]:
    st.subheader('Rastreabilidade de todas as páginas')
    audit=pd.DataFrame([{'Arquivo':p.file,'Página':p.number,'Classificação':p.layout,'Registros':p.records,'OCR':p.ocr,'Confiança OCR':p.confidence,'Erro':p.error,'Competência':p.competence} for p in pages])
    st.dataframe(audit,hide_index=True,use_container_width=True,height=420)
    problem=audit[(audit.Erro!='')|audit.Classificação.str.contains('nenhum|inconclusiva|não identificado',case=False)]
    if not problem.empty:st.warning(f'{len(problem)} páginas requerem atenção; ausência de leitura não confirma falta de colaborador.')
    st.caption('Páginas financeiras ficam separadas das relações. Confiança do OCR é uma métrica do reconhecedor, não garantia de identificação correta.')
    with st.expander('Texto extraído e inspeção de uma página'):
        pindex=st.selectbox('Arquivo/página',range(len(pages)),format_func=lambda i:f'{pages[i].file} · p.{pages[i].number}',key='audit_page')
        p=pages[pindex];st.text_area('Texto',p.text,height=300,disabled=True)
        if st.checkbox('Abrir imagem da página',key='audit_preview'):preview(p.file,p.number)
    with st.expander('Registros sem vínculo na base selecionada — informativo'):
        st.caption('Relações podem abranger toda a empresa. Pessoas de outros contratos não são divergência deste contrato. Esta lista não vai ao pacote do cliente.')
        st.dataframe(pd.DataFrame(st.session_state.outside).drop(columns=['evidence'],errors='ignore'),hide_index=True,use_container_width=True)
    with st.expander('Registro de decisões humanas'):
        st.json(st.session_state.decisions);st.json(st.session_state.base_audit)

with tabs[4]:
    st.subheader('Excel interno + entrega minimizada ao cliente')
    st.caption('O pacote do cliente inclui apenas o escopo selecionado e CPFs parcialmente mascarados. Não inclui relações integrais, dados de outros contratos ou PDFs originais.')
    meta={'Escopo':' | '.join(f'{x[1]} / {x[2]} / {x[0]}' for x in selected),'Revisor':st.session_state.user,'Lote':st.session_state.batch,'VT':st.session_state.config['vt_mode'],'Ponto':st.session_state.config['ponto'],'Pendências':len(pending),'Problemas de processamento':len(st.session_state.errors)}
    if st.button('Preparar planilha interna completa'):
        internal=workbook(rows,scoped,records,pages,st.session_state.decisions,meta=meta,base_audit=st.session_state.base_audit)
        st.session_state['internal_export']=(signature,internal)
    if st.session_state.get('internal_export',('',))[0]==signature:
        st.download_button('Baixar Excel de conferência e auditoria',st.session_state.internal_export[1],'lider_limpe_conferencia_interna.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    checkpoint={'schema':1,'manifest':st.session_state.manifest,'config':st.session_state.config,'decisions':st.session_state.decisions,'manual_records':st.session_state.manual_records,'base':[{'id':e.id,'vt':e.vt,'union':e.union,'warnings':e.warnings} for e in people],'base_audit':st.session_state.base_audit,'saved_at':now()}
    st.download_button('Salvar revisão para continuar depois (JSON interno)',json.dumps(checkpoint,ensure_ascii=False,indent=2).encode(),'lider_limpe_revisao_interna.json','application/json')
    imported=st.file_uploader('Restaurar revisão do mesmo lote',type=['json'],key='checkpoint')
    if imported and st.button('Aplicar revisão salva'):
        try:
            if imported.size>8*1024*1024:raise ValueError('Arquivo de revisão excede 8 MB.')
            cp=json.loads(imported.getvalue())
            if cp.get('schema')!=1 or cp.get('manifest')!=st.session_state.manifest or cp.get('config')!=st.session_state.config:raise ValueError('O arquivo pertence a outro lote/configuração. Recarregue os mesmos PDFs e opções.')
            knownpages={(p.file,p.number) for p in pages};restored=[]
            for raw in cp.get('manual_records',[]):
                r=Record(**raw)
                if (r.file,r.page) not in knownpages or r.benefit!='Ponto':raise ValueError('Registro manual não corresponde ao lote.')
                restored.append(r)
            validids={r.id for r in records+restored}
            if any(d.get('action') not in ['confirm','waive','missing'] or (d.get('action')=='confirm' and d.get('record_id') not in validids) for d in cp.get('decisions',{}).values()):raise ValueError('Decisões contêm registros inválidos.')
            for r in restored:
                if r.id not in {x.id for x in records}:records.append(r)
            st.session_state.manual_records=[asdict(r) for r in restored];st.session_state.decisions=cp.get('decisions',{})
            overrides={e['id']:e for e in cp.get('base',[])}
            for e in people:
                if e.id in overrides:e.vt=bool(overrides[e.id]['vt']);e.union=bool(overrides[e.id]['union']);e.warnings=list(overrides[e.id]['warnings'])
            st.session_state.base_audit=cp.get('base_audit',[]);st.rerun()
        except Exception as exc:st.error(f'Revisão não aplicada: {exc}')
    st.divider()
    authorized=st.checkbox('Sou responsável pela entrega e conferi contrato, competência, base e pendências')
    risk=st.checkbox('Preparar como rascunho COM PENDÊNCIAS, sem liberação de faturamento') if len(pending) or st.session_state.errors else False
    if st.session_state.errors:st.error('Há erros de processamento/escopo. O pacote permanece bloqueado até reprocessar o lote sem esses erros.')
    if st.button('Preparar pacote do cliente',type='primary',disabled=not authorized or bool(st.session_state.errors) or (bool(len(pending)) and not risk)):
        data=client_package(rows,meta['Escopo'],meta)
        st.session_state['client_export']=(signature,data)
    if st.session_state.get('client_export',('',))[0]==signature and authorized and not st.session_state.errors and (not len(pending) or risk):
        st.download_button('Baixar pacote do cliente (Excel + relatório HTML)',st.session_state.client_export[1],'lider_limpe_pacote_cliente.zip','application/zip')
        st.info('Envio manual: revise o pacote e encaminhe pelo canal autorizado. O app não envia e-mail automaticamente. O HTML pode ser aberto no navegador e impresso em PDF.')
    st.warning('Não publique documentos de colaboradores no GitHub. Excel interno e JSON de revisão contêm dados pessoais; armazene com controle de acesso.')
