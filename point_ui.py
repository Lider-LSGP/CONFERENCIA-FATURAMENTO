"""Mesa de revisão visual das folhas de ponto."""
import io,json
from dataclasses import asdict
import streamlit as st
import pandas as pd
import pymupdf as fitz
from engine import uid,norm,name_score
from point_tools import point_workspace,validate_point_link,manual_point_record


def render_point_workspace(people,pages,records,rows,preview,save_decision):
    if st.session_state.pop('point_clear_search',False):st.session_state.pop('point_name_search',None)
    notice=st.session_state.pop('point_notice',None)
    if notice:st.success(notice)
    st.subheader('Mesa de ponto · página de um lado, colaborador do outro')
    st.caption('A ordem alfabética ajuda a localizar, mas NÃO comprova identidade. Confira visualmente cada página antes de vincular.')
    if not st.session_state.config.get('ponto'):
        st.info('Ponto está desabilitado no lote. Marque a opção na aba Documentos e processe novamente para conferir.');return
    pending,completed,allpages,bindings,pointrows=point_workspace(people,pages,records,rows,st.session_state.config.get('categorias',{}))
    a,b,c=st.columns(3);a.metric('Pessoas ainda pendentes no ponto',len(pending));b.metric('Pessoas concluídas no ponto',len(completed));c.metric('Páginas de ponto no escopo',len(allpages))
    if not allpages:st.info('Não há páginas de ponto compatíveis com o escopo selecionado.');return
    show_done=st.checkbox('Mostrar colaboradores já concluídos',False,key='point_show_done')
    only_free=st.checkbox('Mostrar somente páginas ainda sem vínculo',True,key='point_only_free')
    fileoptions=list(dict.fromkeys(p.file for p in allpages))
    filename=st.selectbox('Arquivo de ponto',['Todos os arquivos']+fileoptions,key='point_file_filter')
    visible=[p for p in allpages if (filename=='Todos os arquivos' or p.file==filename) and (not only_free or (p.file,p.number) not in bindings)]
    with st.expander('Lista de todas as páginas numeradas e vínculos',expanded=False):
        st.dataframe(pd.DataFrame([{'Arquivo':p.file,'Página':p.number,'Situação':'Vinculada' if (p.file,p.number) in bindings else 'Sem vínculo','Colaborador vinculado':'; '.join(e.name for e in bindings.get((p.file,p.number),[])),'Competência':p.competence,'Leitura':p.layout} for p in allpages]),hide_index=True,width='stretch',height=260)
    if not visible:
        st.success('Todas as páginas deste filtro têm vínculo. Desmarque o filtro para consultar ou desfazer vínculos.')
        if pending:st.warning(f'Ainda há {len(pending)} pessoas pendentes. Isso não prova ausência: pode faltar documento ou haver página que precise ser obtida/identificada.')
        return
    opts={uid(p.file_hash,p.number):p for p in visible};keys=list(opts)
    queued=st.session_state.pop('point_next_page',None)
    if queued in opts:st.session_state['point_page_id']=queued
    if st.session_state.get('point_page_id') not in opts:st.session_state['point_page_id']=keys[0]
    def choose_page(key):st.session_state['point_page_id']=key
    def move(delta):
        current=st.session_state.get('point_page_id',keys[0]);idx=keys.index(current) if current in keys else 0
        choose_page(keys[max(0,min(len(keys)-1,idx+delta))])
    key=st.selectbox('Página de ponto',keys,format_func=lambda k:f'{opts[k].file} · página {opts[k].number}'+(' · JÁ VINCULADA' if (opts[k].file,opts[k].number) in bindings else ''),key='point_page_id')
    idx=keys.index(key);prev,position,nxt=st.columns([1,2,1])
    prev.button('Página anterior',on_click=move,args=(-1,),disabled=idx==0,key='point_prev')
    position.caption(f'Página {idx+1} de {len(keys)} no filtro · número original: {opts[key].number}')
    nxt.button('Próxima página',on_click=move,args=(1,),disabled=idx==len(keys)-1,key='point_next')
    with st.expander('Galeria de páginas numeradas',expanded=False):
        st.caption('Miniaturas em grupos. Todas as páginas do filtro podem ser acessadas; a imagem completa aparece abaixo.')
        size=st.selectbox('Miniaturas por grupo',[9,18,30],key='point_thumb_size')
        totalgroups=(len(keys)+size-1)//size
        group=st.selectbox('Grupo de miniaturas',list(range(1,totalgroups+1)),key='point_thumb_group')
        slots=st.columns(3);blobs=st.session_state.get('blobs',{})
        for i,k in enumerate(keys[(group-1)*size:group*size]):
            pg=opts[k]
            with slots[i%3]:
                st.caption(f'{pg.file} · p.{pg.number}')
                if pg.file in blobs:
                    try:
                        with fitz.open(stream=blobs[pg.file],filetype='pdf') as doc:st.image(doc[pg.number-1].get_pixmap(dpi=32).tobytes('png'),width='stretch')
                    except Exception:st.caption('Miniatura indisponível. Use visualização completa.')
                st.button(f'Abrir página {pg.number}',key='point_thumb_'+k,on_click=choose_page,args=(k,))
    page=opts[key];left,right=st.columns([1.4,1])
    with left:
        st.markdown(f'**Folha de ponto · página {page.number}**');preview(page.file,page.number)
        page_records=[r for r in records if r.benefit=='Ponto' and r.file==page.file and r.page==page.number]
        if page_records:st.caption('Nomes extraídos (não confirmados só pelo OCR): '+ '; '.join(dict.fromkeys(r.name for r in page_records)))
    with right:
        st.markdown('**Escolha o nome da folha de pagamento**')
        lookup=st.text_input('Buscar nome entre os colaboradores do ponto',key='point_name_search')
        pool=sorted((pending+completed) if show_done else pending,key=lambda e:(norm(e.name),e.competence,e.contract))
        if lookup:pool=[e for e in pool if norm(lookup) in norm(e.name)]
        pool=[e for e in pool if not page.competence or e.competence==page.competence]
        choices={'':None,**{e.id:e for e in pool}}
        person_key=st.selectbox('Colaborador identificado visualmente',list(choices),format_func=lambda k:'Selecione o nome — nenhuma vinculação automática' if not k else f'{choices[k].name} · {choices[k].competence}'+(' · JÁ CONCLUÍDO' if choices[k] in completed else ''),key='point_employee_'+key)
        employee=choices[person_key]
        st.caption(f'{len(pool)} nomes no filtro. Os concluídos ficam ocultos por padrão; dispensas justificadas também contam como concluídas, não como página recebida.')
        occupied=bindings.get((page.file,page.number),[])
        if occupied:
            st.warning('Página já vinculada: '+', '.join(e.name for e in occupied))
            reason=st.text_input('Justificativa para desfazer o vínculo desta página',key='point_undo_note')
            consent=st.checkbox('Conferi e quero desfazer o vínculo',key='point_undo_consent')
            if st.button('Desfazer vínculo desta página',disabled=not consent):
                if not reason.strip():st.error('Informe a justificativa.')
                else:
                    for old in occupied:
                        save_decision(uid(old.id,'Ponto'),'clear','',reason)
                    st.rerun()
        if employee:
            st.write(f'Nome: **{employee.name}**');st.write(f'CPF da folha: {employee.cpf}');st.caption(f'{employee.contract} · {employee.competence}')
            if st.checkbox('Visualizar página da folha de pagamento',key='point_payroll_preview'):preview(employee.file,employee.page)
            previous=pointrows.get(employee.id,{})
            if previous.get('Status') in {'Confirmado','Validado manualmente'}:st.warning('Este colaborador já possui página confirmada. O novo vínculo substituiria o anterior; confira antes.')
        with st.form('point_link_form',clear_on_submit=True):
            note=st.text_area('Evidência visual da identificação',help='Exemplo: conferi o nome digitado no cabeçalho. Não use apenas a posição na ordem alfabética.')
            agree=st.checkbox('Conferi o nome nesta página e na folha de pagamento')
            advance=st.checkbox('Após validar, ir para a próxima página sem vínculo',True)
            submitted=st.form_submit_button('Vincular esta página ao colaborador',type='primary',disabled=employee is None)
        if submitted:
            if not note.strip() or not agree:st.error('Justificativa e confirmação visual são obrigatórias.')
            else:
                try:
                    validate_point_link(employee,page,records,rows)
                    rec=manual_point_record(employee,page,note)
                    if rec.id not in {r.id for r in records}:records.append(rec);st.session_state.manual_records.append(asdict(rec))
                    save_decision(uid(employee.id,'Ponto'),'confirm',rec.id,note)
                    if advance:
                        nextkeys=keys[idx+1:]+keys[:idx]
                        nextfree=next((k for k in nextkeys if (opts[k].file,opts[k].number) not in bindings),None)
                        if nextfree:st.session_state['point_next_page']=nextfree
                    st.session_state['point_clear_search']=True
                    st.session_state['point_notice']=f'{employee.name} vinculado(a) à página {page.number}. Nome oculto da lista de pendentes.'
                    st.rerun()
                except ValueError as exc:st.error(str(exc))
