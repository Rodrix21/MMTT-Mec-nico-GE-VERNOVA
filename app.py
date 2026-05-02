import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats
from scipy.optimize import curve_fit
from datetime import datetime, timedelta
import openpyxl
import io
import os
import zipfile
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="GE Vernova · Análisis de Desgaste",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background:#0a0e1a; color:#e8eaf0; }
  [data-testid="stSidebar"] { background:#0d1220; border-right:1px solid #1e2a45; }
  [data-testid="stSidebar"] * { color:#c8d0e0 !important; }
  .ge-header {
      display:flex; align-items:center; gap:18px;
      padding:18px 28px; margin-bottom:6px;
      background:linear-gradient(90deg,#0d1220 0%,#0f2040 60%,#0d1220 100%);
      border-bottom:2px solid #1565c0; border-radius:0 0 10px 10px;
  }
  .ge-header h1 { margin:0; font-size:1.55rem; font-weight:700;
      color:#e8f0fe; letter-spacing:.03em; }
  .ge-header span { font-size:.85rem; color:#7986cb; font-style:italic; }
  .kpi-grid { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:20px; }
  .kpi-card { flex:1; min-width:140px; background:#111827;
      border:1px solid #1e3a5f; border-radius:10px; padding:14px 18px;
      box-shadow:0 2px 12px rgba(0,0,0,.4); }
  .kpi-label { font-size:.72rem; color:#7986cb; text-transform:uppercase;
      letter-spacing:.08em; margin-bottom:4px; }
  .kpi-value { font-size:1.5rem; font-weight:700; color:#e8f0fe; }
  .kpi-sub   { font-size:.75rem; color:#546e8a; margin-top:2px; }
  .kpi-warn  { color:#ef5350 !important; }
  .kpi-ok    { color:#26c6da !important; }
  .section-title { font-size:1rem; font-weight:600; color:#90caf9;
      border-left:3px solid #1565c0; padding-left:10px; margin:24px 0 10px; }
  [data-testid="stTabs"] button { color:#90caf9 !important; }
  [data-testid="stTabs"] button[aria-selected="true"] {
      border-bottom:2px solid #1565c0 !important; color:#e8f0fe !important; }
  .stSelectbox label,.stSlider label,
  .stMultiSelect label,.stRadio label { color:#90caf9 !important; }
  div[data-baseweb="select"]>div { background:#111827 !important;
      border-color:#1e3a5f !important; color:#e8eaf0 !important; }
  .stPlotlyChart { border-radius:10px; overflow:hidden; }
  hr { border-color:#1e2a45; }
  .module-badge {
      display:inline-block; padding:3px 12px; border-radius:20px;
      font-size:.78rem; font-weight:600; margin-bottom:12px;
  }
  .badge-rodete   { background:#0d2b4e; color:#90caf9; border:1px solid #1565c0; }
  .badge-directriz{ background:#1b2e1e; color:#81c784; border:1px solid #388e3c; }
</style>
""", unsafe_allow_html=True)

DATA_DIR = "data"
DIR_COLS = ["sup_entrada_A", "sup_salida_B", "inf_entrada_A", "inf_salida_B"]
DIR_LABELS = {
    "sup_entrada_A": "Sup. Entrada A",
    "sup_salida_B":  "Sup. Salida B",
    "inf_entrada_A": "Inf. Entrada A",
    "inf_salida_B":  "Inf. Salida B",
}
DIR_COLORS = {
    "sup_entrada_A": "#42a5f5",
    "sup_salida_B":  "#26c6da",
    "inf_entrada_A": "#66bb6a",
    "inf_salida_B":  "#ffa726",
}

# ──────────────────────────────────────────────────────────────
# EXCEL PARSER
# ──────────────────────────────────────────────────────────────
def parse_excel(file_obj):
    wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    sheets_rod = {"UG1": "UG1_MED_ALAB_ROD_PER_SAL", "UG2": "UG2_MED_ALAB_ROD_PER_SAL"}
    sheets_dir = {"UG1": "UG1_MED_HOL_ALAB_DIREC",   "UG2": "UG2_MED_HOL_ALAB_DIREC"}
    result = {}
    for unit, sname in sheets_rod.items():
        ws = wb[sname]; rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 2: continue
            if row[0] is None or not isinstance(row[0], datetime): continue
            rows.append({"fecha": row[0].date(), "punto": row[1],
                         **{f"M{j+1}": row[2+j] for j in range(13)}})
        result[f"rodete_{unit}"] = pd.DataFrame(rows)
    for unit, sname in sheets_dir.items():
        ws = wb[sname]; rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 3: continue
            if row[0] is None or not isinstance(row[0], datetime): continue
            rows.append({"fecha": row[0].date(), "alabe": row[1],
                         "sup_entrada_A": row[2], "sup_salida_B": row[3],
                         "inf_entrada_A": row[4], "inf_salida_B": row[5]})
        result[f"directriz_{unit}"] = pd.DataFrame(rows)
    wb.close()
    return result

# ──────────────────────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────────────────────
@st.cache_data
def load_csv_data():
    data = {}
    for key in ["rodete_UG1","rodete_UG2","directriz_UG1","directriz_UG2"]:
        path = os.path.join(DATA_DIR, f"data_{key}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            df["fecha"] = pd.to_datetime(df["fecha"])
            data[key] = df
    return data

def get_data():
    if "live_data" in st.session_state:
        return st.session_state["live_data"]
    return load_csv_data()

# ──────────────────────────────────────────────────────────────
# REGRESSION HELPERS (shared)
# ──────────────────────────────────────────────────────────────
def days_from_origin(dates):
    t0 = dates.min()
    return (dates - t0).dt.days.values, t0

def _r2(y, yp):
    ss = np.sum((y - np.mean(y))**2)
    return 1 - np.sum((y-yp)**2)/ss if ss > 0 else 0

def _rmse(y, yp):
    return np.sqrt(np.mean((y-yp)**2))

def fit_linear(x, y):
    s, b, *_ = stats.linregress(x, y)
    yp = s*x+b
    return {"name":"Lineal","pred":lambda xx,s=s,b=b:s*xx+b,
            "r2":_r2(y,yp),"rmse":_rmse(y,yp),"color":"#42a5f5"}

def fit_poly(x, y, deg):
    c = np.polyfit(x, y, deg); p = np.poly1d(c); yp = p(x)
    return {"name":f"Polinómica g{deg}","pred":lambda xx,p=p:p(xx),
            "r2":_r2(y,yp),"rmse":_rmse(y,yp),
            "color":"#ab47bc" if deg==2 else "#ce93d8"}

def fit_exp(x, y):
    try:
        def fn(xx,a,b,c): return a*np.exp(b*xx)+c
        popt,_ = curve_fit(fn,x,y,p0=[y.max()-y.min()+.01,-1e-4,y.min()],maxfev=6000)
        yp = fn(x,*popt)
        return {"name":"Exponencial","pred":lambda xx,p=popt:fn(xx,*p),
                "r2":_r2(y,yp),"rmse":_rmse(y,yp),"color":"#ef5350"}
    except: return None

def fit_pow(x, y):
    try:
        def fn(xx,a,b,c): return a*(np.abs(np.where(xx==0,1,xx))**b)+c
        popt,_ = curve_fit(fn,x,y,p0=[1,.5,y.min()],maxfev=6000)
        yp = fn(x,*popt)
        return {"name":"Potencial","pred":lambda xx,p=popt:fn(xx,*p),
                "r2":_r2(y,yp),"rmse":_rmse(y,yp),"color":"#ff7043"}
    except: return None

def get_all_fits(x, y):
    fits = [fit_linear(x,y), fit_poly(x,y,2), fit_poly(x,y,3)]
    for fn in [fit_exp, fit_pow]:
        f = fn(x,y)
        if f: fits.append(f)
    return sorted(fits, key=lambda f:-f["r2"])

def forecast_crossing(fit, x_max, y_target, t0, horizon_days):
    xs = np.linspace(0, x_max+horizon_days, 3000)
    ys = fit["pred"](xs)
    idx = np.where(np.diff(np.sign(ys-y_target)))[0]
    if len(idx): return t0 + timedelta(days=int(xs[idx[0]]))
    return None

BL = dict(
    paper_bgcolor="#111827", plot_bgcolor="#0f1623",
    font=dict(color="#c8d0e0", family="Inter, Arial"),
    xaxis=dict(gridcolor="#1e2a45", linecolor="#1e3a5f", zerolinecolor="#1e3a5f"),
    yaxis=dict(gridcolor="#1e2a45", linecolor="#1e3a5f", zerolinecolor="#1e3a5f"),
    margin=dict(l=50,r=20,t=50,b=50),
    hoverlabel=dict(bgcolor="#0d1220",font_color="#e8eaf0",bordercolor="#1565c0"),
    legend=dict(bgcolor="rgba(0,0,0,0)",bordercolor="#1e2a45",borderwidth=1),
)
PAL = px.colors.qualitative.Set3

def _add_today(fig):
    today_str = datetime.today().strftime("%Y-%m-%d")
    fig.add_shape(type="line", x0=today_str, x1=today_str, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="#546e8a", dash="dot", width=1.5))
    fig.add_annotation(x=today_str, y=1, xref="x", yref="paper",
                       text="Hoy", showarrow=False,
                       font=dict(color="#546e8a", size=11),
                       xanchor="left", yanchor="top")

def _regression_traces(fig, df_s, x, t0, y, sel_fits, threshold, forecast_yrs):
    horizon = int(forecast_yrs*365)
    x_ext   = np.linspace(0, x.max()+horizon, 500)
    d_ext_s = [(t0+timedelta(days=int(d))).strftime("%Y-%m-%d") for d in x_ext]
    forecasts = []
    for fit in sel_fits:
        yf = fit["pred"](x_ext)
        r,g,b = int(fit["color"][1:3],16),int(fit["color"][3:5],16),int(fit["color"][5:7],16)
        fig.add_trace(go.Scatter(
            x=d_ext_s+d_ext_s[::-1],
            y=list(yf+fit["rmse"])+list((yf-fit["rmse"])[::-1]),
            fill="toself", line=dict(color="rgba(0,0,0,0)"),
            fillcolor=f"rgba({r},{g},{b},0.10)",
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=d_ext_s, y=yf, mode="lines",
            name=f"{fit['name']}  R²={fit['r2']:.4f}",
            line=dict(color=fit["color"],width=2.5),
            hovertemplate=f"<b>{fit['name']}</b><br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
        ))
        if threshold > 0:
            fd = forecast_crossing(fit, x.max(), threshold, t0, horizon)
            if fd:
                forecasts.append({"Modelo":fit["name"],
                                   "Fecha estimada":fd.strftime("%Y-%m-%d"),
                                   "R²":round(fit["r2"],4),"RMSE":round(fit["rmse"],4)})
    if threshold > 0:
        fig.add_hline(y=threshold, line_dash="dot", line_color="#ef5350",
                      annotation_text=f"Límite crítico {threshold} mm",
                      annotation_font_color="#ef5350")
    _add_today(fig)
    return sorted(forecasts, key=lambda x:-x["R²"])

def _show_forecasts(forecasts, threshold, forecast_yr):
    if forecasts:
        st.markdown('<div class="section-title">📅 Fechas estimadas de falla</div>',
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(forecasts), use_container_width=True)
        bf = forecasts[0]
        dl = (pd.to_datetime(bf["Fecha estimada"])-pd.Timestamp.today()).days
        msg = (f"Según **{bf['Modelo']}** (R²={bf['R²']:.4f}), se estima alcanzar "
               f"**{threshold} mm** el **{bf['Fecha estimada']}**")
        st.info(f"⏱️ {msg} — en ~**{dl} días** desde hoy.") if dl>0 else \
        st.warning(f"⚠️ {msg} — posiblemente ya alcanzado.")
    elif threshold > 0:
        st.info(f"ℹ️ No se proyecta alcanzar {threshold} mm en {forecast_yr} años "
                "con los modelos seleccionados.")

def color_r2(v):
    if v>=0.95: return "background:#1b5e20;color:#a5d6a7"
    if v>=0.80: return "background:#0d2b4e;color:#90caf9"
    return "background:#3e1e1e;color:#ef9a9a"

# ──────────────────────────────────────────────────────────────
# SIDEBAR — DATA PANEL
# ──────────────────────────────────────────────────────────────
def sidebar_data_panel():
    st.sidebar.markdown("### 📂 Actualizar datos")
    st.sidebar.markdown(
        '<div style="background:#0d1a2e;border:1px dashed #1565c0;border-radius:8px;'
        'padding:12px;margin-bottom:10px">'
        '<p style="color:#7986cb;font-size:.78rem;margin:0">'
        '① Sube el Excel → ② Procesa en memoria → '
        '③ Descarga ZIP → ④ Sube /data a GitHub</p></div>',
        unsafe_allow_html=True,
    )
    uploaded = st.sidebar.file_uploader("Subir .xlsm / .xlsx", type=["xlsm","xlsx"])
    if uploaded is not None:
        with st.sidebar:
            with st.spinner("Procesando…"):
                try:
                    dfs = parse_excel(uploaded)
                    live = {k: pd.DataFrame(df).assign(fecha=lambda d: pd.to_datetime(d["fecha"]))
                            for k, df in dfs.items()}
                    st.session_state["live_data"] = live
                    st.session_state["csv_ready"] = dfs
                    st.success(f"✅ {sum(len(d) for d in dfs.values())} registros procesados")
                except Exception as e:
                    st.error(f"Error: {e}")
    if "csv_ready" in st.session_state:
        st.sidebar.markdown("---")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
            for key, df in st.session_state["csv_ready"].items():
                zf.writestr(f"data/data_{key}.csv", df.to_csv(index=False).encode())
        buf.seek(0)
        st.sidebar.download_button("⬇️ data_vernova.zip", data=buf,
                                    file_name="data_vernova.zip", mime="application/zip")
    st.sidebar.markdown("---")

# ══════════════════════════════════════════════════════════════
# MÓDULO 1 — RODETE
# ══════════════════════════════════════════════════════════════
def rodete_sidebar(rodete_keys):
    st.sidebar.markdown('<span class="module-badge badge-rodete">⚙️ Rodete</span>',
                        unsafe_allow_html=True)
    unit_map   = {k.replace("rodete_","").replace("_","-"): k for k in rodete_keys}
    unit_label = st.sidebar.selectbox("🔧 Unidad Generadora", list(unit_map.keys()), key="rod_unit")
    df_unit    = rodete_keys[unit_map[unit_label]]
    puntos     = sorted(df_unit["punto"].unique())
    punto      = st.sidebar.selectbox("📍 Zona del álabe (D1–D5)", puntos, key="rod_punto")
    df_p       = df_unit[df_unit["punto"]==punto].sort_values("fecha").reset_index(drop=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Regresión")
    reg_opts = ["Lineal","Polinómica g2","Polinómica g3","Exponencial","Potencial"]
    reg_sel  = st.sidebar.multiselect("Modelos", reg_opts,
                                       default=["Lineal","Polinómica g2","Exponencial"],
                                       key="rod_reg")
    med_reg  = st.sidebar.slider("Posición para regresión", 1, 13, 7, key="rod_med")
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚠️ Pronóstico")
    threshold   = st.sidebar.number_input("Espesor límite crítico (mm)", 0.0, 20.0, 14.0, 0.1,
                                           key="rod_thr")
    forecast_yr = st.sidebar.slider("Horizonte (años)", 1, 10, 4, key="rod_fc")
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Vista")
    med_vis = st.sidebar.multiselect("Posiciones a graficar (1–13)",
                                      list(range(1,14)), default=list(range(1,14)),
                                      key="rod_vis")
    return unit_label, df_unit, punto, df_p, reg_sel, med_reg, threshold, forecast_yr, med_vis


def rodete_page(unit_label, df_unit, punto, df_p, reg_sel, med_reg, threshold, forecast_yr, med_vis, rodete_keys):
    m_cols  = [f"M{i}" for i in range(1,14)]
    r_first = df_p.iloc[0]; r_last = df_p.iloc[-1]
    avg_f   = np.nanmean([r_first.get(c,np.nan) for c in m_cols])
    avg_l   = np.nanmean([r_last.get(c,np.nan)  for c in m_cols])
    wear    = avg_f - avg_l
    n_days  = (df_p["fecha"].max() - df_p["fecha"].min()).days
    rate_yr = wear/n_days*365 if n_days > 0 else 0

    kpis = [
        ("Unidad",             unit_label,           "",                                       ""),
        ("Zona analizada",     punto,                 "",                                       ""),
        ("Inspecciones",       len(df_p),             "campañas",                               "kpi-ok"),
        ("Espesor inicial",    f"{avg_f:.3f} mm",     df_p['fecha'].min().strftime('%Y-%m-%d'), ""),
        ("Espesor actual",     f"{avg_l:.3f} mm",     df_p['fecha'].max().strftime('%Y-%m-%d'),
         "kpi-warn" if avg_l < threshold else "kpi-ok"),
        ("Desgaste acumulado", f"{wear:.3f} mm",      "desde primera medición",
         "kpi-warn" if wear > 1 else ""),
        ("Tasa anual",         f"{rate_yr:.3f} mm/a", "promedio histórico",
         "kpi-warn" if rate_yr > 0.3 else ""),
    ]
    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    for col_st,(label,val,sub,cls) in zip(st.columns(len(kpis)), kpis):
        with col_st:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
                        f'<div class="kpi-value {cls}">{val}</div>'
                        f'<div class="kpi-sub">{sub}</div></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    tab1,tab2,tab3,tab4 = st.tabs(["📏 Evolución temporal","📐 Perfil espacial",
                                    "📈 Regresión & Pronóstico","🌡️ Mapa de calor & Desgaste"])

    with tab1:
        st.markdown('<div class="section-title">Evolución del espesor por posición a lo largo del tiempo</div>',
                    unsafe_allow_html=True)
        if med_vis:
            fig = go.Figure()
            for i,m in enumerate(med_vis):
                col = f"M{m}"
                if col not in df_p.columns: continue
                fig.add_trace(go.Scatter(
                    x=df_p["fecha"].dt.strftime("%Y-%m-%d"), y=df_p[col],
                    mode="lines+markers", name=f"Pos {m}",
                    line=dict(color=PAL[i%len(PAL)],width=2), marker=dict(size=7),
                    hovertemplate=f"Pos {m}<br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
                ))
            fig.update_layout(**BL, height=400,
                title=dict(text=f"📏 Evolución temporal — {unit_label} · {punto}",font_size=14,x=0.01),
                xaxis_title="Fecha",yaxis_title="Espesor (mm)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Selecciona al menos una posición en el panel lateral.")
        st.markdown('<div class="section-title">Datos registrados</div>', unsafe_allow_html=True)
        disp = df_p.copy()
        disp["fecha"] = disp["fecha"].dt.strftime("%Y-%m-%d")
        disp.columns  = ["Fecha","Zona"]+[f"Pos {i}" for i in range(1,14)]
        st.dataframe(disp.style.background_gradient(cmap="RdYlGn",
                     subset=[f"Pos {i}" for i in range(1,14)]),
                     use_container_width=True, height=220)

    with tab2:
        st.markdown('<div class="section-title">Perfil espacial por campaña</div>',
                    unsafe_allow_html=True)
        fig2 = go.Figure()
        clrs = ["#42a5f5","#26c6da","#66bb6a","#ffa726","#ef5350"]
        for i,(_,row) in enumerate(df_p.iterrows()):
            vals = [row.get(c,np.nan) for c in m_cols]
            fig2.add_trace(go.Scatter(
                x=[str(j) for j in range(1,14)], y=vals,
                mode="lines+markers", name=row["fecha"].strftime("%Y-%m-%d"),
                line=dict(color=clrs[i%len(clrs)],width=2), marker=dict(size=8),
                fill="tozeroy" if i==0 else "none",
                fillcolor="rgba(66,165,245,0.06)",
                hovertemplate="Pos %{x}: %{y:.3f} mm<extra></extra>",
            ))
        fig2.update_layout(**BL, height=380,
            title=dict(text=f"📐 Perfil espacial — {unit_label} · {punto}",font_size=14,x=0.01),
            xaxis_title="Posición (1→13)",yaxis_title="Espesor (mm)")
        st.plotly_chart(fig2, use_container_width=True)
        c1,c2 = st.columns(2)
        for col_st,row_data,label,color in [
            (c1,r_first,f"Primera — {df_p['fecha'].min().strftime('%Y-%m-%d')}","#42a5f5"),
            (c2,r_last, f"Última  — {df_p['fecha'].max().strftime('%Y-%m-%d')}","#ef5350"),
        ]:
            with col_st:
                st.markdown(f"**{label}**")
                vals = [row_data.get(c,np.nan) for c in m_cols]
                fb = go.Figure(go.Bar(x=[str(i) for i in range(1,14)], y=vals,
                    marker_color=color, hovertemplate="Pos %{x}: %{y:.3f} mm<extra></extra>"))
                fb.update_layout(**BL, height=280, yaxis_title="mm", xaxis_title="Posición",
                    title=dict(text=label,font_size=11))
                st.plotly_chart(fb, use_container_width=True)

    with tab3:
        col = f"M{med_reg}"
        st.markdown(f'<div class="section-title">Regresión — {unit_label} · {punto} · Posición {med_reg}</div>',
                    unsafe_allow_html=True)
        if col in df_p.columns:
            df_s = df_p.sort_values("fecha")
            x, t0 = days_from_origin(df_s["fecha"])
            y = df_s[col].values.astype(float)
            all_fits = get_all_fits(x, y)
            sel_fits = [f for f in all_fits if f["name"] in reg_sel] if reg_sel else all_fits
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=df_s["fecha"].dt.strftime("%Y-%m-%d"), y=y,
                mode="markers", name="Medición real",
                marker=dict(size=11,color="#ffd54f",symbol="circle",
                            line=dict(color="#ff8f00",width=1.5)),
                hovertemplate="Fecha: %{x}<br>%{y:.3f} mm<extra></extra>",
            ))
            forecasts = _regression_traces(fig3, df_s, x, t0, y, sel_fits, threshold, forecast_yr)
            fig3.update_layout(**BL, height=460,
                title=dict(text=f"📈 Regresión — {unit_label}·{punto} · Pos {med_reg}",font_size=14,x=0.01),
                xaxis_title="Fecha",yaxis_title="Espesor (mm)")
            st.plotly_chart(fig3, use_container_width=True)
            _show_forecasts(forecasts, threshold, forecast_yr)

        st.markdown('<div class="section-title">Mejor modelo por posición</div>',
                    unsafe_allow_html=True)
        x_d, _ = days_from_origin(df_p.sort_values("fecha")["fecha"])
        rows_tbl = []
        for i in range(1,14):
            c2 = f"M{i}"
            if c2 not in df_p.columns: continue
            yc = df_p.sort_values("fecha")[c2].values.astype(float)
            if np.any(np.isnan(yc)): continue
            best = get_all_fits(x_d, yc)[0]
            rows_tbl.append({"Posición":i,"Mejor modelo":best["name"],
                              "R²":round(best["r2"],4),"RMSE":round(best["rmse"],4),
                              "Espesor actual (mm)":round(float(df_p.sort_values("fecha")[c2].iloc[-1]),3)})
        if rows_tbl:
            st.dataframe(pd.DataFrame(rows_tbl).style.map(color_r2,subset=["R²"]),
                         use_container_width=True, height=420)

    with tab4:
        # Heatmap
        last = df_unit["fecha"].max()
        df_l = df_unit[df_unit["fecha"]==last]
        puntos_all = sorted(df_l["punto"].unique())
        z = [[df_l[df_l["punto"]==p].iloc[0].get(c,np.nan) for c in m_cols] for p in puntos_all]
        fig_hm = go.Figure(go.Heatmap(
            z=z, x=[str(i) for i in range(1,14)], y=puntos_all,
            colorscale="RdYlGn_r",
            text=[[f"{v:.2f}" for v in row] for row in z],
            texttemplate="%{text}", textfont=dict(size=10,color="#000"),
            hovertemplate="Zona:%{y} Pos:%{x}<br>%{z:.3f} mm<extra></extra>",
            colorbar=dict(title=dict(text="mm",font=dict(color="#c8d0e0")),
                          tickfont=dict(color="#c8d0e0")),
        ))
        fig_hm.update_layout(**BL, height=320,
            title=dict(text=f"🌡️ Mapa de calor — {unit_label} · {pd.Timestamp(last).strftime('%Y-%m-%d')}",
                       font_size=14,x=0.01),
            xaxis_title="Posición (1→13)",yaxis_title="Zona")
        st.markdown('<div class="section-title">Mapa de calor — última inspección</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_hm, use_container_width=True)

        # Delta
        dates_all = sorted(df_unit["fecha"].unique())
        if len(dates_all) >= 2:
            df_f2 = df_unit[df_unit["fecha"]==dates_all[0]]
            df_l2 = df_unit[df_unit["fecha"]==dates_all[-1]]
            clrs2 = ["#42a5f5","#26c6da","#66bb6a","#ffa726","#ef5350"]
            fig_d = go.Figure()
            for i,p in enumerate(sorted(df_unit["punto"].unique())):
                rf=df_f2[df_f2["punto"]==p]; rl=df_l2[df_l2["punto"]==p]
                if rf.empty or rl.empty: continue
                delta=[rf.iloc[0].get(c,np.nan)-rl.iloc[0].get(c,np.nan) for c in m_cols]
                fig_d.add_trace(go.Bar(x=[str(j) for j in range(1,14)], y=delta, name=p,
                    marker_color=clrs2[i%len(clrs2)],
                    hovertemplate=f"Zona {p} Pos %{{x}}<br>Δ=%{{y:.3f}} mm<extra></extra>"))
            fig_d.update_layout(**BL, barmode="group", height=360,
                title=dict(text=f"📉 Desgaste acumulado — {unit_label} "
                                f"({pd.Timestamp(dates_all[0]).strftime('%Y-%m-%d')} → "
                                f"{pd.Timestamp(dates_all[-1]).strftime('%Y-%m-%d')})",
                           font_size=14,x=0.01),
                xaxis_title="Posición",yaxis_title="Reducción de espesor (mm)")
            st.markdown('<div class="section-title">Desgaste acumulado total</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_d, use_container_width=True)

        # UG1 vs UG2
        st.markdown('<div class="section-title">Comparativo UG-1 vs UG-2</div>',
                    unsafe_allow_html=True)
        comp_rows = []
        for k,df_u in rodete_keys.items():
            ul = k.replace("rodete_","").replace("_","-")
            for p in sorted(df_u["punto"].unique()):
                for _,row in df_u[df_u["punto"]==p].iterrows():
                    comp_rows.append({"Unidad":ul,"Zona":p,"Fecha":row["fecha"],
                                      "Avg":np.nanmean([row.get(c,np.nan) for c in m_cols])})
        comp_df = pd.DataFrame(comp_rows)
        fig_cmp = go.Figure()
        ug_c  = {"UG-1":"#42a5f5","UG-2":"#ef5350"}
        dashes = ["solid","dash","dot","dashdot","longdash"]
        for ug in ["UG-1","UG-2"]:
            for j,p in enumerate(sorted(comp_df["Zona"].unique())):
                sub = comp_df[(comp_df["Unidad"]==ug)&(comp_df["Zona"]==p)].sort_values("Fecha")
                fig_cmp.add_trace(go.Scatter(
                    x=sub["Fecha"].dt.strftime("%Y-%m-%d"), y=sub["Avg"],
                    mode="lines+markers", name=f"{ug}·{p}",
                    line=dict(color=ug_c[ug],width=2,dash=dashes[j%len(dashes)]),
                    marker=dict(size=7),
                    hovertemplate=f"{ug} {p}<br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
                ))
        fig_cmp.update_layout(**BL, height=420,
            title=dict(text="Espesor promedio UG-1 vs UG-2 por zona",font_size=14,x=0.01),
            xaxis_title="Fecha",yaxis_title="Espesor promedio (mm)")
        st.plotly_chart(fig_cmp, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# MÓDULO 2 — DIRECTRICES
# ══════════════════════════════════════════════════════════════
def directriz_sidebar(dir_keys):
    st.sidebar.markdown('<span class="module-badge badge-directriz">🔩 Directrices</span>',
                        unsafe_allow_html=True)
    unit_map   = {k.replace("directriz_","").replace("_","-"): k for k in dir_keys}
    unit_label = st.sidebar.selectbox("🔧 Unidad Generadora", list(unit_map.keys()), key="dir_unit")
    df_unit    = dir_keys[unit_map[unit_label]]

    alabes = sorted(df_unit["alabe"].unique())
    alabe  = st.sidebar.selectbox("🔢 Álabe (1–20)", alabes, key="dir_alabe")
    df_a   = df_unit[df_unit["alabe"]==alabe].sort_values("fecha").reset_index(drop=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Regresión")
    punto_reg = st.sidebar.selectbox("Punto de medida",
                                      list(DIR_LABELS.values()),
                                      key="dir_punto_reg")
    col_reg = {v:k for k,v in DIR_LABELS.items()}[punto_reg]
    reg_opts  = ["Lineal","Polinómica g2","Polinómica g3","Exponencial","Potencial"]
    reg_sel   = st.sidebar.multiselect("Modelos", reg_opts,
                                        default=["Lineal","Polinómica g2","Exponencial"],
                                        key="dir_reg")
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚠️ Pronóstico")
    threshold   = st.sidebar.number_input("Holgura límite crítica (mm)", 0.0, 5.0, 0.15, 0.01,
                                           key="dir_thr")
    forecast_yr = st.sidebar.slider("Horizonte (años)", 1, 10, 4, key="dir_fc")
    return unit_label, df_unit, alabe, df_a, col_reg, punto_reg, reg_sel, threshold, forecast_yr


def directriz_page(unit_label, df_unit, alabe, df_a, col_reg, punto_reg, reg_sel, threshold, forecast_yr, dir_keys):
    # KPIs
    r_first = df_a.iloc[0]; r_last = df_a.iloc[-1]
    avg_f   = np.nanmean([r_first.get(c,np.nan) for c in DIR_COLS])
    avg_l   = np.nanmean([r_last.get(c,np.nan)  for c in DIR_COLS])
    wear    = avg_f - avg_l
    n_days  = (df_a["fecha"].max() - df_a["fecha"].min()).days
    rate_yr = wear/n_days*365 if n_days > 0 else 0

    kpis = [
        ("Unidad",              unit_label,             "",                                        ""),
        ("Álabe analizado",     f"#{alabe}",             "",                                        ""),
        ("Inspecciones",        len(df_a),               "campañas",                                "kpi-ok"),
        ("Holgura inicial prom",f"{avg_f:.3f} mm",       df_a['fecha'].min().strftime('%Y-%m-%d'),  ""),
        ("Holgura actual prom", f"{avg_l:.3f} mm",       df_a['fecha'].max().strftime('%Y-%m-%d'),
         "kpi-warn" if avg_l < threshold else "kpi-ok"),
        ("Variación acumulada", f"{wear:.3f} mm",        "desde primera medición",
         "kpi-warn" if abs(wear) > 0.1 else ""),
        ("Tasa anual",          f"{rate_yr:.3f} mm/a",   "promedio histórico",
         "kpi-warn" if abs(rate_yr) > 0.05 else ""),
    ]
    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    for col_st,(label,val,sub,cls) in zip(st.columns(len(kpis)), kpis):
        with col_st:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
                        f'<div class="kpi-value {cls}">{val}</div>'
                        f'<div class="kpi-sub">{sub}</div></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    tab1,tab2,tab3,tab4 = st.tabs(["📏 Evolución temporal","📐 Perfil por álabe",
                                    "📈 Regresión & Pronóstico","🌡️ Mapa de calor & Comparativo"])

    with tab1:
        st.markdown('<div class="section-title">Evolución de holguras en los 4 puntos de medida</div>',
                    unsafe_allow_html=True)
        fig1 = go.Figure()
        for col,label in DIR_LABELS.items():
            if col not in df_a.columns: continue
            fig1.add_trace(go.Scatter(
                x=df_a["fecha"].dt.strftime("%Y-%m-%d"), y=df_a[col],
                mode="lines+markers", name=label,
                line=dict(color=DIR_COLORS[col],width=2), marker=dict(size=8),
                hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
            ))
        fig1.update_layout(**BL, height=400,
            title=dict(text=f"📏 Evolución holguras — {unit_label} · Álabe #{alabe}",font_size=14,x=0.01),
            xaxis_title="Fecha",yaxis_title="Holgura (mm)")
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown('<div class="section-title">Datos registrados</div>', unsafe_allow_html=True)
        disp = df_a.copy()
        disp["fecha"] = disp["fecha"].dt.strftime("%Y-%m-%d")
        disp = disp[["fecha","alabe"]+DIR_COLS]
        disp.columns = ["Fecha","Álabe"] + list(DIR_LABELS.values())
        st.dataframe(disp.style.background_gradient(cmap="RdYlGn_r",
                     subset=list(DIR_LABELS.values())),
                     use_container_width=True, height=260)

    with tab2:
        st.markdown('<div class="section-title">Holgura por punto de medida en cada campaña — todos los álabes</div>',
                    unsafe_allow_html=True)
        punto_vis = st.selectbox("Ver punto de medida", list(DIR_LABELS.values()), key="dir_tab2_punto")
        col_vis   = {v:k for k,v in DIR_LABELS.items()}[punto_vis]

        fechas_all = sorted(df_unit["fecha"].unique())
        clrs = ["#42a5f5","#26c6da","#66bb6a","#ffa726","#ef5350","#ab47bc","#ff7043"]
        fig2 = go.Figure()
        for i,f in enumerate(fechas_all):
            df_f = df_unit[df_unit["fecha"]==f].sort_values("alabe")
            fig2.add_trace(go.Scatter(
                x=df_f["alabe"].astype(str), y=df_f[col_vis],
                mode="lines+markers", name=pd.Timestamp(f).strftime("%Y-%m-%d"),
                line=dict(color=clrs[i%len(clrs)],width=2), marker=dict(size=7),
                hovertemplate=f"Álabe %{{x}}<br>%{{y:.3f}} mm<extra></extra>",
            ))
        fig2.update_layout(**BL, height=400,
            title=dict(text=f"📐 {punto_vis} — todos los álabes por campaña — {unit_label}",
                       font_size=14,x=0.01),
            xaxis_title="N° Álabe",yaxis_title="Holgura (mm)")
        st.plotly_chart(fig2, use_container_width=True)

        # Primera vs última campaña lado a lado
        c1,c2 = st.columns(2)
        for col_st,fecha,label,color in [
            (c1, fechas_all[0],  f"Primera — {pd.Timestamp(fechas_all[0]).strftime('%Y-%m-%d')}","#42a5f5"),
            (c2, fechas_all[-1], f"Última  — {pd.Timestamp(fechas_all[-1]).strftime('%Y-%m-%d')}","#ef5350"),
        ]:
            with col_st:
                st.markdown(f"**{label}**")
                df_snap = df_unit[df_unit["fecha"]==fecha].sort_values("alabe")
                fb = go.Figure()
                for col,lbl in DIR_LABELS.items():
                    fb.add_trace(go.Bar(
                        x=df_snap["alabe"].astype(str), y=df_snap[col],
                        name=lbl, marker_color=DIR_COLORS[col],
                        hovertemplate=f"{lbl} Álabe %{{x}}: %{{y:.3f}} mm<extra></extra>",
                    ))
                fb.update_layout(**BL, barmode="group", height=300,
                    yaxis_title="mm", xaxis_title="N° Álabe",
                    title=dict(text=label,font_size=11))
                st.plotly_chart(fb, use_container_width=True)

    with tab3:
        st.markdown(f'<div class="section-title">Regresión — {unit_label} · Álabe #{alabe} · {punto_reg}</div>',
                    unsafe_allow_html=True)
        if col_reg in df_a.columns:
            df_s = df_a.sort_values("fecha")
            x, t0 = days_from_origin(df_s["fecha"])
            y = df_s[col_reg].values.astype(float)
            all_fits = get_all_fits(x, y)
            sel_fits = [f for f in all_fits if f["name"] in reg_sel] if reg_sel else all_fits
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=df_s["fecha"].dt.strftime("%Y-%m-%d"), y=y,
                mode="markers", name="Medición real",
                marker=dict(size=11,color="#ffd54f",symbol="circle",
                            line=dict(color="#ff8f00",width=1.5)),
                hovertemplate="Fecha: %{x}<br>%{y:.3f} mm<extra></extra>",
            ))
            forecasts = _regression_traces(fig3, df_s, x, t0, y, sel_fits, threshold, forecast_yr)
            fig3.update_layout(**BL, height=460,
                title=dict(text=f"📈 Regresión — {unit_label} · Álabe #{alabe} · {punto_reg}",
                           font_size=14,x=0.01),
                xaxis_title="Fecha",yaxis_title="Holgura (mm)")
            st.plotly_chart(fig3, use_container_width=True)
            _show_forecasts(forecasts, threshold, forecast_yr)

        # Tabla de mejor modelo por punto de medida para este álabe
        st.markdown('<div class="section-title">Mejor modelo por punto de medida</div>',
                    unsafe_allow_html=True)
        x_d, _ = days_from_origin(df_a.sort_values("fecha")["fecha"])
        rows_tbl = []
        for col,lbl in DIR_LABELS.items():
            if col not in df_a.columns: continue
            yc = df_a.sort_values("fecha")[col].values.astype(float)
            if np.any(np.isnan(yc)): continue
            best = get_all_fits(x_d, yc)[0]
            rows_tbl.append({"Punto":lbl,"Mejor modelo":best["name"],
                              "R²":round(best["r2"],4),"RMSE":round(best["rmse"],4),
                              "Holgura actual (mm)":round(float(df_a.sort_values("fecha")[col].iloc[-1]),3)})
        if rows_tbl:
            st.dataframe(pd.DataFrame(rows_tbl).style.map(color_r2,subset=["R²"]),
                         use_container_width=True, height=220)

    with tab4:
        # Heatmap: álabes × puntos de medida en última campaña
        st.markdown('<div class="section-title">Mapa de calor — última inspección (todos los álabes × 4 puntos)</div>',
                    unsafe_allow_html=True)
        last = df_unit["fecha"].max()
        df_last = df_unit[df_unit["fecha"]==last].sort_values("alabe")
        z_hm   = [[row.get(c,np.nan) for c in DIR_COLS] for _,row in df_last.iterrows()]
        fig_hm = go.Figure(go.Heatmap(
            z=z_hm,
            x=list(DIR_LABELS.values()),
            y=df_last["alabe"].astype(str).tolist(),
            colorscale="RdYlGn_r",
            text=[[f"{v:.3f}" for v in row] for row in z_hm],
            texttemplate="%{text}", textfont=dict(size=9,color="#000"),
            hovertemplate="Álabe %{y} · %{x}<br>%{z:.3f} mm<extra></extra>",
            colorbar=dict(title=dict(text="mm",font=dict(color="#c8d0e0")),
                          tickfont=dict(color="#c8d0e0")),
        ))
        fig_hm.update_layout(**BL, height=520,
            title=dict(text=f"🌡️ Mapa de calor — {unit_label} · {pd.Timestamp(last).strftime('%Y-%m-%d')}",
                       font_size=14,x=0.01),
            xaxis_title="Punto de medida",yaxis_title="N° Álabe")
        st.plotly_chart(fig_hm, use_container_width=True)

        # Comparativo UG1 vs UG2 — holgura promedio por álabe
        st.markdown('<div class="section-title">Comparativo UG-1 vs UG-2 — holgura promedio por álabe</div>',
                    unsafe_allow_html=True)
        comp_rows = []
        for k,df_u in dir_keys.items():
            ul = k.replace("directriz_","").replace("_","-")
            for _,row in df_u.iterrows():
                comp_rows.append({"Unidad":ul,"Álabe":row["alabe"],"Fecha":row["fecha"],
                                   "Avg":np.nanmean([row.get(c,np.nan) for c in DIR_COLS])})
        comp_df = pd.DataFrame(comp_rows)
        fig_cmp = go.Figure()
        ug_c = {"UG-1":"#42a5f5","UG-2":"#ef5350"}
        for ug in ["UG-1","UG-2"]:
            sub = comp_df[comp_df["Unidad"]==ug].groupby("Fecha")["Avg"].mean().reset_index()
            sub = sub.sort_values("Fecha")
            fig_cmp.add_trace(go.Scatter(
                x=sub["Fecha"].dt.strftime("%Y-%m-%d"), y=sub["Avg"],
                mode="lines+markers", name=ug,
                line=dict(color=ug_c[ug],width=2), marker=dict(size=7),
                hovertemplate=f"{ug}<br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
            ))
        fig_cmp.update_layout(**BL, height=360,
            title=dict(text="Holgura promedio global UG-1 vs UG-2",font_size=14,x=0.01),
            xaxis_title="Fecha",yaxis_title="Holgura promedio (mm)")
        st.plotly_chart(fig_cmp, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    st.markdown("""
    <div class="ge-header">
      <div>
        <h1>⚡ GE Vernova — Monitoreo de Desgaste</h1>
        <span>Rodete · Álabes Directrices · Tendencias y Pronóstico de Falla</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    sidebar_data_panel()

    data = get_data()
    rodete_keys  = {k: v for k, v in data.items() if k.startswith("rodete_")}
    dir_keys     = {k: v for k, v in data.items() if k.startswith("directriz_")}

    if not rodete_keys and not dir_keys:
        st.warning("⚠️ No hay datos. Sube el Excel en el panel lateral o agrega los CSV a /data.")
        st.stop()

    # ── Selector de módulo (arriba del sidebar)
    with st.sidebar:
        st.markdown("### 🗂️ Módulo de análisis")
        modulo = st.radio("", ["⚙️ Rodete", "🔩 Directrices"],
                          label_visibility="collapsed", key="modulo")
        st.markdown("---")
        st.markdown("### ⚙️ Panel de Control")
        st.markdown("---")

        if modulo == "⚙️ Rodete" and rodete_keys:
            params = rodete_sidebar(rodete_keys)
        elif modulo == "🔩 Directrices" and dir_keys:
            params = directriz_sidebar(dir_keys)
        else:
            st.info("Datos no disponibles para este módulo.")
            st.stop()

    if modulo == "⚙️ Rodete":
        rodete_page(*params, rodete_keys)
    else:
        directriz_page(*params, dir_keys)


if __name__ == "__main__":
    main()
