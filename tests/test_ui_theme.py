from pathlib import Path
import tomllib
from ui_theme import THEME_CSS

ROOT=Path(__file__).parents[1]

def luminance(color):
    parts=[int(color[i:i+2],16)/255 for i in [1,3,5]]
    parts=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in parts]
    return .2126*parts[0]+.7152*parts[1]+.0722*parts[2]

def ratio(a,b):
    x,y=luminance(a),luminance(b)
    return (max(x,y)+.05)/(min(x,y)+.05)


def test_theme_base_is_explicit_light():
    settings=tomllib.loads((ROOT/'.streamlit/config.toml').read_text())
    assert settings['theme']['base']=='light'
    assert settings['theme']['textColor']=='#153358'


def test_palette_body_and_primary_button_have_aa_contrast():
    for fg,bg in [('#153358','#FFFFFF'),('#435775','#F4F7FB'),('#FFFFFF','#B84B00'),('#FFFFFF','#092E65'),('#D9E5F8','#092E65'),('#4B5D78','#E8EDF5')]:
        assert ratio(fg,bg)>=4.5,(fg,bg,ratio(fg,bg))


def test_canvas_overlay_is_transparent_and_title_children_white():
    assert '.dvn-scroller { background: transparent !important; }' in THEME_CSS
    assert '.hero h1 :is(span,a,svg) { color: #FFFFFF !important; }' in THEME_CSS
    assert '--gdg-text-dark: #153358' in THEME_CSS


def test_no_global_white_rule_for_all_sidebar_children():
    assert 'section[data-testid="stSidebar"] *' not in THEME_CSS


def test_matrix_and_chart_own_foreground():
    source=(ROOT/'app.py').read_text()
    assert 'color: #153358; background-color:' in source
    assert "st.altair_chart(chart,theme=None" in source
    assert "labelColor='#153358'" in source
