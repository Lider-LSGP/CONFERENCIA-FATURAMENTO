import pymupdf as fitz
from engine import extract_pdf,parse_records,Person,reconcile
from pdf_highlights import marked_pdf_zip
import io,zipfile


def test_right_aligned_value_and_matricula_before_header():
    d=fitz.open();p=d.new_page()
    for x,text in [(39,'Cartao'),(128,'Nome'),(284,'Centro'),(320,'de'),(331,'Custo'),(378,'Matricula'),(450,'Valor'),(508,'Assinatura')]:p.insert_text((x,100),text,fontsize=8)
    for x,text in [(39,'6392XXXXXXXX1234'),(128,'MARIA HELENA MATOS'),(284,'TVV'),(365,'0'),(445,'735,46')]:p.insert_text((x,125),text,fontsize=8)
    data=d.tobytes();d.close();rs=parse_records(extract_pdf('VA.pdf',data,'h',ocr=False),'VA')
    assert rs[0].name=='MARIA HELENA MATOS';assert rs[0].center_cost=='TVV';assert rs[0].registration=='0';assert rs[0].amount==735.46


def test_existing_highlight_preserved_not_duplicated():
    d=fitz.open();p=d.new_page();p.insert_text((120,90),'MARIA HELENA MATOS')
    words=p.get_text('words');boxes=[list(w[:4]) for w in words];a=p.add_highlight_annot([fitz.Rect(b) for b in boxes]);a.update();data=d.tobytes();d.close()
    from engine import Record
    person=Person('e','MARIA HELENA MATOS','52998224725','1','EMPRESA','03.659.631/0001-05','CONTRATO','08/2026','ASG',False,False,'folha.pdf',1,'')
    r=Record('r','VA',person.name,'','VA.pdf',1,'',boxes=boxes)
    row={'colaborador_id':'e','Benefício':'VA','Obrigatório':True,'Status':'Confirmado','registro_id':'r'}
    pages=extract_pdf('VA.pdf',data,'h',ocr=False)
    blob,log=marked_pdf_zip({'VA.pdf':data},[person],[r],pages,[row])
    with zipfile.ZipFile(io.BytesIO(blob)) as z:assert z.read('VA.pdf')==data
    assert log[0][4]=='JÁ MARCADO'
