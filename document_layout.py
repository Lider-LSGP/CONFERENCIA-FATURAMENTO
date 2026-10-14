"""Extração por posição de colunas: Centro de Custo nunca entra no nome."""
import re
from engine import norm


def rows_from_words(words,rotation=0,width=0,height=0):
    # As caixas armazenadas são sempre no espaço nativo do PDF (não rotacionado).
    import pymupdf as fitz
    visual=[]
    for w in words:
        if len(w)<5:continue
        box=fitz.Rect(w[:4])
        if rotation:
            if rotation==90:box=fitz.Rect(height-box.y1,box.x0,height-box.y0,box.x1)
            elif rotation==180:box=fitz.Rect(width-box.x1,height-box.y1,width-box.x0,height-box.y0)
            elif rotation==270:box=fitz.Rect(box.y0,width-box.x1,box.y1,width-box.x0)
        visual.append({'text':str(w[4]),'box':list(w[:4]),'visual':list(box),'y':(box.y0+box.y1)/2})
    buckets=[]
    for word in sorted(visual,key=lambda w:(w['y'],w['visual'][0])):
        if buckets and abs(buckets[-1][0]-word['y'])<3.5:buckets[-1][1].append(word)
        else:buckets.append([word['y'],[word]])
    return [sorted(g,key=lambda w:w['visual'][0]) for _,g in buckets]


def parse_va_columns(page):
    rows=rows_from_words(getattr(page,'words',[]),getattr(page,'rotation',0),getattr(page,'width',0),getattr(page,'height',0))
    header=None
    for row in rows:
        labels={norm(w['text']):w for w in row}
        if all(key in labels for key in ['NOME','CENTRO','CUSTO','VALOR','MATRICULA']):header=labels;break
    if not header:return None
    name_left=header['NOME']['visual'][0]-2;name_right=header['CENTRO']['visual'][0]-2
    cc_left=name_right
    # Matrícula/Valor têm títulos centralizados e dados que começam antes deles.
    # As margens usam a largura do próprio título, não um corte rígido em x0.
    cc_right=header['MATRICULA']['visual'][0]-max(8,(header['MATRICULA']['visual'][2]-header['MATRICULA']['visual'][0])/2)
    reg_left=cc_right;reg_right=header['VALOR']['visual'][0]-max(8,(header['VALOR']['visual'][2]-header['VALOR']['visual'][0])/2)
    val_left=reg_right;val_right=header.get('ASSINATURA',{'visual':[1e6]})['visual'][0]-2
    result=[]
    for row in rows:
        card=next((w for w in row if re.fullmatch(r'\d{4}[Xx*]+\d{4}',w['text'])),None)
        if not card:continue
        def column(a,b):return [w for w in row if a<=w['visual'][0]<b]
        name_words=column(name_left,name_right);cc_words=column(cc_left,cc_right)
        names=' '.join(w['text'] for w in name_words).strip()
        money=' '.join(w['text'] for w in column(val_left,val_right))
        match=re.search(r'-?\d[\d.]*[,.]\d{2}',money)
        amount=None
        if match:
            raw=match.group();amount=float(raw.replace('.','').replace(',','.')) if ',' in raw else float(raw)
        result.append({'name':names,'center_cost':' '.join(w['text'] for w in cc_words),'registration':' '.join(w['text'] for w in column(reg_left,reg_right)),'amount':amount,'boxes':[w['box'] for w in name_words],'evidence':' '.join(w['text'] for w in row),'card':card['text']})
    return result
