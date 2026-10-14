"""Tema explícito de alto contraste: não depende de extensões do navegador."""

THEME_CSS = r'''
<style>
:root { color-scheme: light; }
.stApp {
  --ll-bg: #F4F7FB; --ll-paper: #FFFFFF; --ll-text: #153358;
  --ll-muted: #435775; --ll-line: #CCD6E5; --ll-navy: #092E65;
  --ll-accent: #B84B00; --ll-accent-text: #983A00;
  --text-color: #153358; --background-color: #F4F7FB;
  --secondary-background-color: #FFFFFF; --primary-color: #B84B00;
  background: var(--ll-bg) !important; color: var(--ll-text) !important;
  color-scheme: light !important;
}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: #F4F7FB !important; color: #153358 !important;
}
[data-testid="stHeader"] { background: #F4F7FB !important; color: #153358 !important; }
[data-testid="stToolbar"], [data-testid="stToolbar"] button,
[data-testid="stMainMenu"] button { color: #153358 !important; }
.block-container { padding-top: 1.7rem; max-width: 1580px; }
[data-testid="stMain"] :is(h1,h2,h3,h4,h5,h6) { color: #0A3067 !important; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"] :is(p,li,span,strong,em),
[data-testid="stMain"] [data-testid="stWidgetLabel"] :is(p,label,span),
[data-testid="stMain"] label, [data-testid="stMain"] legend {
  color: #153358 !important;
}
[data-testid="stMain"] [data-testid="stCaptionContainer"] :is(p,span),
[data-testid="stMain"] small { color: #435775 !important; opacity: 1 !important; }
[data-testid="stMain"] a { color: #07559E !important; text-decoration-color: #07559E !important; }
/* Campos: inclui texto normal, desabilitado, placeholder e seletores. */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  background: #FFFFFF !important; color: #153358 !important; border-color: #A9BAD1 !important;
}
.stApp input:not([type="checkbox"]):not([type="radio"]), .stApp textarea,
[data-baseweb="select"] input, [data-baseweb="select"] [role="combobox"] {
  background: #FFFFFF !important; color: #153358 !important;
  -webkit-text-fill-color: #153358 !important; caret-color: #153358 !important;
}
.stApp input::placeholder, .stApp textarea::placeholder {
  color: #526580 !important; -webkit-text-fill-color: #526580 !important; opacity: 1 !important;
}
.stApp input:disabled, .stApp textarea:disabled {
  background: #EDF1F6 !important; color: #465873 !important;
  -webkit-text-fill-color: #465873 !important; opacity: 1 !important;
}
[data-baseweb="select"] :is(span,div), [data-baseweb="select"] svg { color: #153358; }
/* Os menus são portais: podem ficar fora da barra lateral. */
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"],
[data-baseweb="popover"] > div { background: #FFFFFF !important; color: #153358 !important; }
[data-baseweb="menu"] :is(li,span,div), [role="option"],
[role="option"] :is(span,div), [data-baseweb="popover"] [role="menuitem"] {
  color: #153358 !important;
}
[role="option"]:hover, [role="option"][aria-selected="true"],
[data-baseweb="menu"] li:hover { background: #E5EDF8 !important; color: #153358 !important; }
[data-baseweb="tag"] { background: #B84B00 !important; color: #FFFFFF !important; }
[data-baseweb="tag"] :is(span,div,svg) { color: #FFFFFF !important; }
/* Botões: laranja escuro com contraste AA, não branco sobre laranja claro. */
.stApp button { color: #153358; }
[data-testid="stButton"] > button, [data-testid="stDownloadButton"] > button,
[data-testid="stFormSubmitButton"] > button, [data-testid="stFileUploader"] button {
  background: #FFFFFF !important; border: 1px solid #9BAEC8 !important;
  color: #153358 !important; border-radius: 10px;
}
[data-testid="stButton"] > button *, [data-testid="stDownloadButton"] > button *,
[data-testid="stFormSubmitButton"] > button *, [data-testid="stFileUploader"] button * {
  color: inherit !important;
}
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stDownloadButton"] > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: #B84B00 !important; border-color: #B84B00 !important; color: #FFFFFF !important;
}
[data-testid="stButton"] > button:hover, [data-testid="stDownloadButton"] > button:hover,
[data-testid="stFormSubmitButton"] > button:hover { border-color: #B84B00 !important; }
.stApp button:disabled { background: #E8EDF5 !important; color: #4B5D78 !important; opacity: 1 !important; }
.stApp button:disabled * { color: #4B5D78 !important; }
/* Abas, caixas, formulários, avisos e arquivos. */
[data-testid="stTabs"] button { color: #435775 !important; font-weight: 600; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #983A00 !important; }
[data-testid="stTabs"] button * { color: inherit !important; }
[data-testid="stExpander"] details, [data-testid="stForm"] {
  border-color: #CCD6E5 !important; color: #153358 !important; background: #F4F7FB !important;
}
[data-testid="stExpander"] summary { color: #153358 !important; background: #F4F7FB !important; }
[data-testid="stExpander"] summary * { color: #153358 !important; }
[data-testid="stFileUploaderDropzone"] { background: #FFFFFF !important; color: #153358 !important; border-color: #A9BAD1 !important; }
[data-testid="stFileUploaderDropzone"] :is(p,span,small,svg),
[data-testid="stFileUploaderFile"] :is(p,span,small) { color: #153358 !important; }
[data-testid="stCheckbox"] :is(label,p,span), [data-testid="stRadio"] :is(label,p,span) {
  color: #153358 !important;
}
[data-testid="stCheckbox"] [role="checkbox"] { accent-color: #B84B00; }
[data-testid="stAlert"] { color: #153358 !important; }
[data-testid="stAlert"] [data-baseweb="notification"] { background: #EAF1FC !important; color: #153358 !important; border: 1px solid #A9BAD1; }
[data-testid="stAlert"] :is(p,span,li,strong) { color: #153358 !important; }
[data-testid="stCode"], [data-testid="stCode"] pre, [data-testid="stJson"] {
  background: #EAF0F8 !important; color: #153358 !important;
}
[data-testid="stCode"] code, [data-testid="stJson"] * { color: #153358 !important; }
[data-testid="stTooltipContent"], [role="tooltip"] {
  background: #153358 !important; color: #FFFFFF !important;
}
[data-testid="stTooltipContent"] *, [role="tooltip"] * { color: #FFFFFF !important; }
/* Indicadores e tabelas, inclusive a grade/canvas usada pelo Streamlit. */
[data-testid="stMetric"] { background: #FFFFFF !important; border: 1px solid #CCD6E5; border-top: 4px solid #F47A00; border-radius: 16px; padding: 18px; }
[data-testid="stMetricLabel"], [data-testid="stMetricValue"],
[data-testid="stMetricLabel"] *, [data-testid="stMetricValue"] * { color: #153358 !important; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"], .dvn-scroller, .glideDataEditor {
  color: #153358 !important; background: #FFFFFF !important;
  --gdg-text-dark: #153358 !important; --gdg-text-medium: #435775 !important;
  --gdg-text-light: #526580 !important; --gdg-text-header: #153358 !important;
  --gdg-text-header-selected: #FFFFFF !important; --gdg-text-group-header: #153358 !important;
  --gdg-bg-cell: #FFFFFF !important; --gdg-bg-cell-medium: #F3F6FB !important;
  --gdg-bg-header: #E5EDF8 !important; --gdg-bg-header-hovered: #D6E4F7 !important;
  --gdg-bg-header-has-focus: #D6E4F7 !important; --gdg-bg-group-header: #E5EDF8 !important;
  --gdg-bg-group-header-hovered: #D6E4F7 !important; --gdg-border-color: #CCD6E5 !important;
  --gdg-accent-color: #07559E !important; --gdg-accent-light: #DDEBFA !important;
  --gdg-accent-fg: #FFFFFF !important; --gdg-link-color: #07559E !important;
}
[data-testid="stTable"] table { background: #FFFFFF !important; color: #153358 !important; }
[data-testid="stTable"] :is(th,td) { color: #153358 !important; border-color: #CCD6E5 !important; }
/* Barra lateral: textos claros sobre azul, campos e escolhas escuros sobre branco. */
section[data-testid="stSidebar"] { background: #092E65 !important; color: #FFFFFF !important; }
section[data-testid="stSidebar"] :is(label,legend),
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
section[data-testid="stSidebar"] :is(h1,h2,h3,h4),
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] :is(p,li,span,strong),
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] :is(p,span,label) { color: #FFFFFF !important; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] :is(p,span) { color: #D9E5F8 !important; opacity: 1 !important; }
section[data-testid="stSidebar"] [data-baseweb="select"] :is(div,span),
section[data-testid="stSidebar"] input { color: #153358 !important; }
section[data-testid="stSidebar"] [data-baseweb="tag"] :is(div,span,svg) { color: #FFFFFF !important; }
section[data-testid="stSidebar"] [data-testid="stButton"] > button {
  background: #16437B !important; color: #FFFFFF !important; border-color: #708CB2 !important;
}
section[data-testid="stSidebar"] [data-testid="stButton"] > button * { color: #FFFFFF !important; }
section[data-testid="stSidebar"] [data-testid="stAlert"] [data-baseweb="notification"] { background: #16437B !important; border-color: #45668E !important; }
section[data-testid="stSidebar"] [data-testid="stAlert"] :is(p,span,li,strong) { color: #FFFFFF !important; }
/* Exceções intencionais: capa azul com escrita branca. */
.hero { background: linear-gradient(120deg,#05275C,#104782); color: #FFFFFF !important; padding: 27px 32px; border-radius: 22px; margin-bottom: 22px; }
[data-testid="stMain"] .hero h1 { color: #FFFFFF !important; font-size: 2.05rem; margin: 0; }
[data-testid="stMain"] .hero h1 :is(span,a,svg) { color: #FFFFFF !important; }
.dvn-scroller { background: transparent !important; }
[data-testid="stMain"] .hero p { color: #E0EBFA !important; margin: 8px 0 0; }
:focus-visible { outline: 3px solid #07559E !important; outline-offset: 2px; }
footer { visibility: hidden; }
</style>
'''
