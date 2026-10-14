from pathlib import Path
from streamlit.testing.v1 import AppTest
import pymupdf as fitz
from engine import Person,Page,uid

ROOT=Path(__file__).parents[1]

def test_visual_point_binding_hides_name_and_advances(monkeypatch):
    monkeypatch.delenv('LIDER_LOCAL_DEV',raising=False)
    app=AppTest.from_file(str(ROOT/'app.py'))
    a=Person('a','ANA LUCIA SILVA','52998224725','1','LIDER','03.659.631/0001-05','20 - PMVV','08/2026','GUARDA VIDAS',False,False,'folha.pdf',1,'synthetic')
    b=Person('b','BRUNO HENRIQUE MATOS','11144477735','2','LIDER','03.659.631/0001-05','20 - PMVV','08/2026','GUARDA VIDAS',False,False,'folha.pdf',1,'synthetic')
    pages=[Page('ponto.pdf','ph',i,'',[],True,0,layout='Ponto: nome não identificado; revisão visual necessária',competence='08/2026') for i in [1,2]]
    doc=fitz.open();doc.new_page().insert_text((30,50),'Colaborador: ANA LUCIA SILVA');doc.new_page().insert_text((30,50),'Colaborador: BRUNO HENRIQUE MATOS');blob=doc.tobytes();doc.close()
    state={'people':[a,b],'records':[],'pages':pages,'blobs':{'ponto.pdf':blob},'batch':'testpoint','decisions':{},'errors':[],'messages':[],'base_audit':[],'config':{'ponto':True,'vt_mode':'Qualquer operadora','dpi':180,'ocr':False,'categorias':{'ponto.pdf':'Ponto'}},'manifest':{'ponto.pdf':'ph'},'manual_records':[]}
    for key,value in state.items():app.session_state[key]=value
    app.run(timeout=25);assert not app.exception
    select=next(x for x in app.selectbox if x.label=='Colaborador identificado visualmente');select.set_value('a').run(timeout=25)
    assert not app.exception
    next(x for x in app.text_area if x.label=='Evidência visual da identificação').input('Conferi o cabeçalho e o nome na folha.')
    next(x for x in app.checkbox if x.label=='Conferi o nome nesta página e na folha de pagamento').check()
    next(x for x in app.button if x.label=='Vincular esta página ao colaborador').click().run(timeout=25)
    assert not app.exception
    assert next(x for x in app.metric if x.label=='Pessoas ainda pendentes no ponto').value=='1'
    assert next(x for x in app.metric if x.label=='Pessoas concluídas no ponto').value=='1'
    remaining=next(x for x in app.selectbox if x.label=='Colaborador identificado visualmente')
    assert not any('ANA LUCIA' in str(x) for x in remaining.options)
    assert any('BRUNO' in str(x) for x in remaining.options)
    assert app.session_state['point_page_id']==uid('ph',2)
    # Voltar a exibir concluídos/páginas vinculadas e desfazer o vínculo.
    next(x for x in app.checkbox if x.label=='Mostrar somente páginas ainda sem vínculo').uncheck().run(timeout=25)
    next(x for x in app.selectbox if x.label=='Página de ponto').set_value(uid('ph',1)).run(timeout=25)
    next(x for x in app.text_input if x.label=='Justificativa para desfazer o vínculo desta página').input('Correção de vinculação para nova revisão.')
    next(x for x in app.checkbox if x.label=='Conferi e quero desfazer o vínculo').check().run(timeout=25)
    next(x for x in app.button if x.label=='Desfazer vínculo desta página').click().run(timeout=25)
    assert not app.exception
    assert next(x for x in app.metric if x.label=='Pessoas ainda pendentes no ponto').value=='2'
    assert next(x for x in app.metric if x.label=='Pessoas concluídas no ponto').value=='0'
    assert app.session_state['decision_history'][-1]['nova']['action']=='clear'
