from pathlib import Path
import pymupdf as fitz
from streamlit.testing.v1 import AppTest
from engine import Person,Record,Page,uid

ROOT=Path(__file__).parents[1]

def seed(app,values):
    for key,value in values.items():app.session_state[key]=value

def test_auth_blocks_without_secret(monkeypatch):
    monkeypatch.delenv('LIDER_LOCAL_DEV',raising=False)
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=25)
    assert not app.exception
    assert any('Acesso bloqueado' in item.value for item in app.error)

def test_full_ui_and_excel(monkeypatch):
    monkeypatch.setenv('LIDER_LOCAL_DEV','1')
    app=AppTest.from_file(str(ROOT/'app.py'))
    e=Person('person1','MARIA HELENA MATOS','52998224725','1','EMPRESA TESTE','03.659.631/0001-05','13 - DORIO','08/2026','AUX SERVICOS GERAIS',False,False,'folha.pdf',1,'synthetic')
    rs=[Record(uid(b),'VA' if b=='VA' else b,e.name,e.cpf if b in ['Odonto','Seguro de vida'] else '',f'{b}.pdf',1,'synthetic',competence=e.competence) for b in ['VA','Saúde','Odonto','Seguro de vida','Idesbre']]
    pp=[Page('folha.pdf','hash',1,'synthetic',['synthetic'],layout='Folha Domínio',records=1)]
    seed(app,{'people':[e],'records':rs,'pages':pp,'blobs':{},'batch':'test','decisions':{},'errors':[],'messages':[],'base_audit':[],'config':{'ponto':False,'vt_mode':'Qualquer operadora','dpi':180,'ocr':False},'manifest':{'folha.pdf':'hash'},'manual_records':[]})
    app.run(timeout=25)
    assert not app.exception
    assert app.metric[0].value=='1'
    assert app.metric[3].value=='0'
    button=next(b for b in app.button if b.label=='Preparar planilha interna completa')
    button.click().run(timeout=25)
    assert not app.exception


def test_pending_review_ui(monkeypatch):
    monkeypatch.setenv('LIDER_LOCAL_DEV','1')
    app=AppTest.from_file(str(ROOT/'app.py'))
    e=Person('p2','MARIA HELENA MATOS','52998224725','1','EMPRESA TESTE','03.659.631/0001-05','13 - DORIO','08/2026','AUX SERVICOS GERAIS',True,True,'folha.pdf',1,'synthetic')
    rs=[Record('r2','VA','MARIA H MATOS','','VA.pdf',1,'synthetic',competence=e.competence)]
    pp=[Page('folha.pdf','hash',1,'synthetic',['synthetic'],layout='Folha Domínio',records=1),Page('VA.pdf','hash2',1,'synthetic',['synthetic'],layout='Relação · VA',records=1)]
    seed(app,{'people':[e],'records':rs,'pages':pp,'blobs':{},'batch':'test','decisions':{},'errors':[],'messages':[],'base_audit':[],'config':{'ponto':False,'vt_mode':'Qualquer operadora','dpi':180,'ocr':False},'manifest':{},'manual_records':[]})
    app.run(timeout=25)
    assert not app.exception
    assert int(app.metric[3].value)>0
    assert any('Conferência'==s.label for s in app.selectbox)
