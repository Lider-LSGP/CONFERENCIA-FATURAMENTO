"""Ponto rápido: escolher nome, vincular, avançar. Sem justificativa/flag obrigatória."""
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
    st.subheader('Ponto rápido · escolha o nome e vincule')
    st.caption('Sem flag ou justificativa obrigatória. O clique em Vincular registra sua decisão, seu nome e o horário. A ordem alfabética ajuda a procurar, mas não comprova identidade.')
    if not st.session_state.config.get('ponto'):st.info('Ponto está desabilitado no lote.');return
    pending,completed,allpages,bindings,pointrows=point_workspace(people,pages,records,rows,st.session_state.config.get('categorias',{}))
    a,b,c=st.columns(3);a.metric('Pessoas ainda pendentes no ponto',len(pending));b.metric('Pessoas concluídas no ponto',len(completed));c.metric('Páginas de ponto no escopo',len(allpages))
    if not allpages:st.info('Nenhuma página de ponto compatível com o escopo.');return
    c1,c2,c3=st.columns(3)
    person_filter=c1.selectbox('Pessoas para exibir',['Pendentes','Todas','Concluídas'],key='point_people_mode')
    page_filter=c2.selectbox('Páginas para exibir',['Sem vínculo','Todas','Vinculadas'],key='point_pages_mode')
    filename=c3.selectbox('Arquivo de ponto',['Todos os arquivos']+list(dict.fromkeys(p.file for p in allpages)),key='point_file_filter')
    visible=[p for p in allpages if (filename=='Todos os arquivos' or p.file==filename) and (page_filter=='Todas' or ((p.file,p.number) in bindings)==(page_filter=='Vinculadas'))]
    with st.expander('Lista de todas as páginas numeradas e vínculos'):
        st.dataframe(pd.DataFrame([{'Arquivo':p.file,'Página':p.number,'Situação':'Vinculada' if (p.file,p.number) in bindings else 'Sem vínculo','Colaborador vinculado':'; '.join(e.name for e in bindings.get((p.file,p.number),[])),'Competência':p.competence} for p in allpages]).style.set_properties(**{'color':'#153358','background-color':'#FFFFFF'}),hide_index=True,width='stretch',height=240)
    if not visible:st.info('Nenhuma página neste filtro. Use Todas para consultar os vínculos.');return
    opts={uid(p.file_hash,p.number):p for p in visible};keys=list(opts)
    queued=st.session_state.pop('point_next_page',None)
    if queued in opts:st.session_state['point_page_id']=queued
    if st.session_state.get('point_page_id') not in opts:st.session_state['point_page_id']=keys[0]
    def choose(key):st.session_state['point_page_id']=key
    def move(delta):
        now=st.session_state.get('point_page_id',keys[0]);idx=keys.index(now) if now in keys else 0
        choose(keys[max(0,min(len(keys)-1,idx+delta))])
    key=st.selectbox('Página de ponto',keys,format_func=lambda k:f'{opts[k].file} · página {opts[k].number}'+(' · vinculada' if (opts[k].file,opts[k].number) in bindings else ''),key='point_page_id')
    idx=keys.index(key);prev,position,nxt=st.columns([1,2,1]);prev.button('Página anterior',on_click=move,args=(-1,),disabled=idx==0,key='point_prev');position.caption(f'{idx+1}/{len(keys)} no filtro · página original {opts[key].number}');nxt.button('Próxima página',on_click=move,args=(1,),disabled=idx==len(keys)-1,key='point_next')
    with st.expander('Galeria de páginas numeradas'):
        size=st.selectbox('Miniaturas por grupo',[9,18,30],key='point_thumb_size');group=st.selectbox('Grupo de miniaturas',list(range(1,(len(keys)+size-1)//size+1)),key='point_thumb_group');slots=st.columns(3)
        for i,k in enumerate(keys[(group-1)*size:group*size]):
            pg=opts[k]
            with slots[i%3]:
                st.caption(f'{pg.file} · p.{pg.number}')
                data=st.session_state.get('blobs',{}).get(pg.file)
                if data:
                    with fitz.open(stream=data,filetype='pdf') as doc:st.image(doc[pg.number-1].get_pixmap(dpi=32).tobytes('png'),width='stretch')
                st.button(f'Abrir página {pg.number}',key='point_thumb_'+k,on_click=choose,args=(k,))
    page=opts[key]
    def link(employee,note='Vinculação visual rápida pelo conferente.'):
        try:
            validate_point_link(employee,page,records,rows)
            rec=manual_point_record(employee,page,note)
            area=st.session_state.get('point_areas',{}).get(uid(page.file_hash,page.number))
            if area:rec.boxes=[area]
            previous=next((r for r in records if r.id==rec.id),None)
            if previous:previous.boxes=rec.boxes or previous.boxes
            else:records.append(rec);st.session_state.manual_records.append(asdict(rec))
            for raw in st.session_state.manual_records:
                if raw['id']==rec.id:raw['boxes']=rec.boxes or raw.get('boxes',[])
            save_decision(uid(employee.id,'Ponto'),'confirm',rec.id,note)
            nextfree=next((k for k in keys[idx+1:]+keys[:idx] if (opts[k].file,opts[k].number) not in bindings),None)
            if nextfree:st.session_state['point_next_page']=nextfree
            st.session_state['point_clear_search']=True;st.session_state['point_notice']=f'{employee.name} vinculado(a) à página {page.number}. Avanço automático para a próxima página livre.';st.rerun()
        except ValueError as exc:st.error(str(exc))
    left,right=st.columns([1.35,1])
    with left:
        st.markdown(f'**Página {page.number} · confira o nome na imagem**');preview(page.file,page.number)
    with right:
        st.markdown('**Nomes da folha de pagamento**')
        pool=sorted(pending if person_filter=='Pendentes' else completed if person_filter=='Concluídas' else pending+completed,key=lambda e:(norm(e.name),e.competence,e.contract))
        pool=[e for e in pool if not page.competence or e.competence==page.competence]
        found=[r for r in records if r.benefit=='Ponto' and r.file==page.file and r.page==page.number and not r.id.startswith('manual')]
        suggestions=sorted([(max((name_score(e.name,r.name) for r in found),default=0),e) for e in pool],key=lambda x:x[0],reverse=True)[:3]
        if suggestions and suggestions[0][0]>=75:
            st.caption('Atalhos sugeridos pelo texto reconhecido — confira a imagem antes de clicar.')
            for score,employee in suggestions:
                if score<75:continue
                if st.button('Vincular '+employee.name,key='point_fast_'+key+'_'+employee.id):link(employee)
        search=st.text_input('Buscar nome entre os colaboradores do ponto',key='point_name_search')
        if search:pool=[e for e in pool if norm(search) in norm(e.name)]
        choices={'':None,**{e.id:e for e in pool}}
        employee_key=st.selectbox('Colaborador identificado visualmente',list(choices),format_func=lambda k:'Escolha o nome' if not k else choices[k].name+' · '+choices[k].competence,key='point_employee_'+key)
        employee=choices[employee_key]
        st.caption(f'{len(pool)} nomes no filtro. Concluídos ficam ocultos em Pendentes.')
        if employee:
            st.write(f'CPF da folha: {employee.cpf}');st.caption(employee.contract)
            with st.expander('Comparar com a folha de pagamento'):preview(employee.file,employee.page)
        if st.button('Vincular esta página ao colaborador',type='primary',disabled=employee is None,key='point_bind_'+key):link(employee)
        occupied=bindings.get((page.file,page.number),[])
        if occupied:
            st.info('Vínculo atual: '+', '.join(e.name for e in occupied))
            if st.button('Desfazer vínculo desta página',key='point_unbind_'+key):
                for old in occupied:save_decision(uid(old.id,'Ponto'),'clear','','Vínculo de ponto desfeito pelo conferente.')
                st.rerun()
        with st.expander('Observação opcional / área do marca-texto'):
            st.caption('Sem obrigatoriedade. Em papel manuscrito/ilegível, indique a região do nome se quiser que o PDF final tenha marca-texto nessa área.')
            observation=st.text_input('Observação do vínculo (opcional)',key='point_optional_note_'+key)
            if employee and observation and st.button('Vincular com esta observação',key='point_bind_note_'+key):link(employee,observation)
            data=st.session_state.get('blobs',{}).get(page.file)
            if data:
                x=st.slider('Área: esquerda (%)',0.,95.,30.,1.,key='mark_x_'+key);y=st.slider('Área: topo (%)',0.,95.,15.,1.,key='mark_y_'+key);w=st.slider('Área: largura (%)',1.,95.,60.,1.,key='mark_w_'+key);h=st.slider('Área: altura (%)',1.,20.,3.,1.,key='mark_h_'+key)
                with fitz.open(stream=data,filetype='pdf') as doc:
                    pdfpage=doc[page.number-1];view=fitz.Rect(pdfpage.rect.width*x/100,pdfpage.rect.height*y/100,pdfpage.rect.width*min(100,x+w)/100,pdfpage.rect.height*min(100,y+h)/100);native=view*pdfpage.derotation_matrix
                    annotation=pdfpage.add_highlight_annot(native);annotation.set_colors(stroke=(1,.85,0));annotation.set_opacity(.35);annotation.update();st.image(pdfpage.get_pixmap(dpi=75).tobytes('png'),caption='Prévia da área escolhida (a origem não é alterada)',width='stretch')
                if st.button('Salvar área do nome para esta página',key='point_save_area_'+key):
                    st.session_state.setdefault('point_areas',{})[uid(page.file_hash,page.number)]=list(native)
                    for r in records:
                        if r.benefit=='Ponto' and r.file==page.file and r.page==page.number and any(d.get('record_id')==r.id and d.get('action')=='confirm' for d in st.session_state.decisions.values()):r.boxes=[list(native)]
                    for raw in st.session_state.manual_records:
                        if raw['file']==page.file and raw['page']==page.number:raw['boxes']=[list(native)]
                    st.session_state.pop('pdf_export',None);st.success('Área salva para o PDF final. Clique em Vincular se a página ainda estiver pendente.')
