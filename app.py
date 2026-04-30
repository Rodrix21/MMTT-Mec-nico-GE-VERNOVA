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

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GE Vernova · Análisis de Desgaste",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
# CUSTOM CSS
# ──────────────────────────────────────────────────────────────
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
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# PATHS — CSV data folder (committed to GitHub)
# ──────────────────────────────────────────────────────────────
DATA_DIR = "data"


# ──────────────────────────────────────────────────────────────
# EXCEL PARSER
# ──────────────────────────────────────────────────────────────
def parse_excel(file_obj):
    """
    Lee el .xlsm y devuelve un dict de DataFrames:
      rodete_UG1, rodete_UG2, directriz_UG1, directriz_UG2
    """
    wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)

    sheets_rod = {"UG1": "UG1_MED_ALAB_ROD_PER_SAL",
                  "UG2": "UG2_MED_ALAB_ROD_PER_SAL"}
    sheets_dir = {"UG1": "UG1_MED_HOL_ALAB_DIREC",
                  "UG2": "UG2_MED_HOL_ALAB_DIREC"}
    result = {}

    for unit, sname in sheets_rod.items():
        ws = wb[sname]
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 2:
                continue
            if row[0] is None or not isinstance(row[0], datetime):
                continue
            rows.append({"fecha": row[0].date(), "punto": row[1],
                         **{f"M{j+1}": row[2+j] for j in range(13)}})
        result[f"rodete_{unit}"] = pd.DataFrame(rows)

    for unit, sname in sheets_dir.items():
        ws = wb[sname]
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 2:
                continue
            if row[0] is None or not isinstance(row[0], datetime):
                continue
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
    """Carga los CSVs que viven en /data del repo."""
    data = {}
    for key in ["rodete_UG1", "rodete_UG2", "directriz_UG1", "directriz_UG2"]:
        path = os.path.join(DATA_DIR, f"data_{key}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            df["fecha"] = pd.to_datetime(df["fecha"])
            data[key] = df
    return data


def get_data():
    """Prioridad: datos procesados en sesión > CSVs del repo."""
    if "live_data" in st.session_state:
        return st.session_state["live_data"]
    return load_csv_data()


# ──────────────────────────────────────────────────────────────
# REGRESSION HELPERS
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
    c = np.polyfit(x, y, deg)
    p = np.poly1d(c)
    yp = p(x)
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
    except Exception:
        return None


def fit_pow(x, y):
    try:
        def fn(xx,a,b,c): return a*(np.abs(np.where(xx==0,1,xx))**b)+c
        popt,_ = curve_fit(fn,x,y,p0=[1,.5,y.min()],maxfev=6000)
        yp = fn(x,*popt)
        return {"name":"Potencial","pred":lambda xx,p=popt:fn(xx,*p),
                "r2":_r2(y,yp),"rmse":_rmse(y,yp),"color":"#ff7043"}
    except Exception:
        return None


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
    if len(idx):
        return t0 + timedelta(days=int(xs[idx[0]]))
    return None


# ──────────────────────────────────────────────────────────────
# PLOT HELPERS
# ──────────────────────────────────────────────────────────────
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


def fig_evolution(df_p, title, medidas):
    fig = go.Figure()
    for i, m in enumerate(medidas):
        col = f"M{m}"
        if col not in df_p.columns: continue
        fig.add_trace(go.Scatter(
            x=df_p["fecha"].dt.strftime("%Y-%m-%d"), y=df_p[col],
            mode="lines+markers", name=f"Pos {m}",
            line=dict(color=PAL[i%len(PAL)],width=2), marker=dict(size=7),
            hovertemplate=f"Pos {m}<br>%{{x}}<br>%{{y:.3f}} mm<extra></extra>",
        ))
    fig.update_layout(**BL, height=400,
        title=dict(text=f"📏 Evolución temporal — {title}",font_size=14,x=0.01),
        xaxis_title="Fecha",yaxis_title="Espesor (mm)")
    return fig


def fig_spatial(df_p, title):
    fig = go.Figure()
    cols = [f"M{i}" for i in range(1,14)]
    clrs = ["#42a5f5","#26c6da","#66bb6a","#ffa726","#ef5350"]
    for i,(_, row) in enumerate(df_p.iterrows()):
        vals = [row.get(c,np.nan) for c in cols]
        fig.add_trace(go.Scatter(
            x=[str(j) for j in range(1,14)], y=vals,
            mode="lines+markers", name=row["fecha"].strftime("%Y-%m-%d"),
            line=dict(color=clrs[i%len(clrs)],width=2), marker=dict(size=8),
            fill="tozeroy" if i==0 else "none",
            fillcolor="rgba(66,165,245,0.06)",
            hovertemplate="Pos %{x}: %{y:.3f} mm<extra></extra>",
        ))
    fig.update_layout(**BL, height=380,
        title=dict(text=f"📐 Perfil espacial por campaña — {title}",font_size=14,x=0.01),
        xaxis_title="Posición (1→13)",yaxis_title="Espesor (mm)")
    return fig


def fig_regression(df_p, title, med_idx, reg_names, threshold, forecast_yrs):
    col = f"M{med_idx}"
    if col not in df_p.columns: return None, []

    df_s = df_p.sort_values("fecha")
    x, t0 = days_from_origin(df_s["fecha"])
    y = df_s[col].values.astype(float)

    all_fits = get_all_fits(x, y)
    sel_fits = [f for f in all_fits if f["name"] in reg_names] if reg_names else all_fits

    horizon = int(forecast_yrs*365)
    x_ext   = np.linspace(0, x.max()+horizon, 500)
    d_ext_s = [(t0+timedelta(days=int(d))).strftime("%Y-%m-%d") for d in x_ext]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_s["fecha"].dt.strftime("%Y-%m-%d"), y=y,
        mode="markers", name="Medición real",
        marker=dict(size=11,color="#ffd54f",symbol="circle",
                    line=dict(color="#ff8f00",width=1.5)),
        hovertemplate="Fecha: %{x}<br>Espesor: %{y:.3f} mm<extra></extra>",
    ))

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
    today_str = datetime.today().strftime("%Y-%m-%d")
fig.add_shape(type="line",
              x0=today_str, x1=today_str, y0=0, y1=1,
              xref="x", yref="paper",
              line=dict(color="#546e8a", dash="dot", width=1.5))
fig.add_annotation(x=today_str, y=1, xref="x", yref="paper",
                   text="Hoy", showarrow=False,
                   font=dict(color="#546e8a", size=11),
                   xanchor="left", yanchor="top")
    fig.update_layout(**BL, height=460,
        title=dict(text=f"📈 Regresión y pronóstico — {title} · Pos {med_idx}",font_size=14,x=0.01),
        xaxis_title="Fecha",yaxis_title="Espesor (mm)")
    return fig, sorted(forecasts, key=lambda x:-x["R²"])


def fig_heatmap(df_unit, unit_label):
    last = df_unit["fecha"].max()
    df_l = df_unit[df_unit["fecha"]==last]
    cols = [f"M{i}" for i in range(1,14)]
    puntos = sorted(df_l["punto"].unique())
    z = [[df_l[df_l["punto"]==p].iloc[0].get(c,np.nan) for c in cols] for p in puntos]
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(i) for i in range(1,14)], y=puntos,
        colorscale="RdYlGn_r",
        text=[[f"{v:.2f}" for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=10,color="#000"),
        hovertemplate="Zona:%{y} Pos:%{x}<br>%{z:.3f} mm<extra></extra>",
        colorbar=dict(title="mm",tickfont=dict(color="#c8d0e0"),titlefont=dict(color="#c8d0e0")),
    ))
    fig.update_layout(**BL, height=320,
        title=dict(text=f"🌡️ Mapa de calor — {unit_label} · {pd.Timestamp(last).strftime('%Y-%m-%d')}",
                   font_size=14,x=0.01),
        xaxis_title="Posición (1→13)",yaxis_title="Zona")
    return fig


def fig_delta(df_unit, unit_label):
    dates = sorted(df_unit["fecha"].unique())
    if len(dates) < 2: return None
    df_f = df_unit[df_unit["fecha"]==dates[0]]
    df_l = df_unit[df_unit["fecha"]==dates[-1]]
    cols = [f"M{i}" for i in range(1,14)]
    clrs = ["#42a5f5","#26c6da","#66bb6a","#ffa726","#ef5350"]
    fig = go.Figure()
    for i,p in enumerate(sorted(df_unit["punto"].unique())):
        rf=df_f[df_f["punto"]==p]; rl=df_l[df_l["punto"]==p]
        if rf.empty or rl.empty: continue
        delta=[rf.iloc[0].get(c,np.nan)-rl.iloc[0].get(c,np.nan) for c in cols]
        fig.add_trace(go.Bar(
            x=[str(j) for j in range(1,14)], y=delta, name=p,
            marker_color=clrs[i%len(clrs)],
            hovertemplate=f"Zona {p} Pos %{{x}}<br>Δ=%{{y:.3f}} mm<extra></extra>",
        ))
    fig.update_layout(**BL, barmode="group", height=360,
        title=dict(text=f"📉 Desgaste acumulado — {unit_label} "
                        f"({pd.Timestamp(dates[0]).strftime('%Y-%m-%d')} → "
                        f"{pd.Timestamp(dates[-1]).strftime('%Y-%m-%d')})",
                   font_size=14,x=0.01),
        xaxis_title="Posición",yaxis_title="Reducción de espesor (mm)")
    return fig


# ──────────────────────────────────────────────────────────────
# SIDEBAR — DATA MANAGEMENT PANEL
# ──────────────────────────────────────────────────────────────
def sidebar_data_panel():
    st.sidebar.markdown("### 📂 Actualizar datos")
    st.sidebar.markdown(
        '<div style="background:#0d1a2e;border:1px dashed #1565c0;border-radius:8px;'
        'padding:12px;margin-bottom:10px">'
        '<p style="color:#7986cb;font-size:.78rem;margin:0">'
        '① Sube el Excel → ② Se procesa en memoria → '
        '③ Descarga el ZIP con los CSV → ④ Súbelos a la carpeta '
        '<code style="color:#90caf9">/data</code> del repo en GitHub.</p></div>',
        unsafe_allow_html=True,
    )

    uploaded = st.sidebar.file_uploader(
        "Subir .xlsm / .xlsx",
        type=["xlsm","xlsx"],
        help="El archivo no se almacena en el servidor. Solo se procesa en tu sesión.",
    )

    if uploaded is not None:
        with st.sidebar:
            with st.spinner("Procesando…"):
                try:
                    dfs = parse_excel(uploaded)
                    live = {k: pd.DataFrame(df).assign(fecha=lambda d: pd.to_datetime(d["fecha"]))
                            for k, df in dfs.items()}
                    st.session_state["live_data"] = live
                    st.session_state["csv_ready"] = dfs
                    total = sum(len(d) for d in dfs.values())
                    st.success(f"✅ {total} registros procesados")
                except Exception as e:
                    st.error(f"Error: {e}")

    if "csv_ready" in st.session_state:
        st.sidebar.markdown("---")
        st.sidebar.markdown(
            '<p style="color:#90caf9;font-size:.82rem;margin-bottom:6px">'
            '📥 Descarga los CSV para el repo</p>',
            unsafe_allow_html=True,
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
            for key, df in st.session_state["csv_ready"].items():
                zf.writestr(f"data/data_{key}.csv", df.to_csv(index=False).encode())
        buf.seek(0)
        st.sidebar.download_button(
            "⬇️ data_vernova.zip",
            data=buf, file_name="data_vernova.zip", mime="application/zip",
        )

    st.sidebar.markdown("---")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
def main():
    st.markdown("""
    <div class="ge-header">
      <div>
        <h1>⚡ GE Vernova — Monitoreo de Desgaste</h1>
        <span>Álabe del Rodete · Perfil de Salida · Análisis de Tendencias y Pronóstico de Falla</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    sidebar_data_panel()

    data = get_data()
    rodete_keys = {k: v for k, v in data.items() if k.startswith("rodete_")}

    if not rodete_keys:
        st.warning(
            "⚠️ No hay datos cargados. Usa el panel lateral para subir el Excel, "
            "o asegúrate de que los CSV estén en la carpeta `/data` del repositorio."
        )
        st.stop()

    # ── Sidebar controls
    with st.sidebar:
        st.markdown("### ⚙️ Panel de Control")
        st.markdown("---")

        unit_map   = {k.replace("rodete_","").replace("_","-"): k for k in rodete_keys}
        unit_label = st.selectbox("🔧 Unidad Generadora", list(unit_map.keys()))
        df_unit    = rodete_keys[unit_map[unit_label]]

        puntos = sorted(df_unit["punto"].unique())
        punto  = st.selectbox("📍 Zona del álabe (D1–D5)", puntos)
        df_p   = df_unit[df_unit["punto"]==punto].sort_values("fecha").reset_index(drop=True)

        st.markdown("---")
        st.markdown("### 📊 Regresión")
        reg_opts = ["Lineal","Polinómica g2","Polinómica g3","Exponencial","Potencial"]
        reg_sel  = st.multiselect("Modelos",reg_opts,
                                   default=["Lineal","Polinómica g2","Exponencial"])
        med_reg  = st.slider("Posición para regresión", 1, 13, 7)

        st.markdown("---")
        st.markdown("### ⚠️ Pronóstico de Falla")
        threshold   = st.number_input("Espesor límite crítico (mm)", 0.0, 20.0, 14.0, 0.1)
        forecast_yr = st.slider("Horizonte (años)", 1, 10, 4)

        st.markdown("---")
        st.markdown("### 🔍 Vista")
        med_vis = st.multiselect("Posiciones a graficar (1–13)",
                                  list(range(1,14)), default=list(range(1,14)))

    # ── KPIs
    m_cols  = [f"M{i}" for i in range(1,14)]
    r_first = df_p.iloc[0]; r_last = df_p.iloc[-1]
    avg_f   = np.nanmean([r_first.get(c,np.nan) for c in m_cols])
    avg_l   = np.nanmean([r_last.get(c,np.nan)  for c in m_cols])
    wear    = avg_f - avg_l
    n_days  = (df_p["fecha"].max() - df_p["fecha"].min()).days
    rate_yr = wear/n_days*365 if n_days > 0 else 0

    kpis = [
        ("Unidad",             unit_label,           "",                                        ""),
        ("Zona analizada",     punto,                 "",                                        ""),
        ("Inspecciones",       len(df_p),             "campañas",                                "kpi-ok"),
        ("Espesor inicial",    f"{avg_f:.3f} mm",     df_p['fecha'].min().strftime('%Y-%m-%d'),  ""),
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
            st.markdown(f"""
            <div class="kpi-card">
              <div class="kpi-label">{label}</div>
              <div class="kpi-value {cls}">{val}</div>
              <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Tabs
    tab1,tab2,tab3,tab4 = st.tabs([
        "📏 Evolución temporal",
        "📐 Perfil espacial",
        "📈 Regresión & Pronóstico",
        "🌡️ Mapa de calor & Desgaste",
    ])

    with tab1:
        st.markdown('<div class="section-title">Evolución del espesor por posición a lo largo del tiempo</div>',
                    unsafe_allow_html=True)
        if med_vis:
            st.plotly_chart(fig_evolution(df_p, f"{unit_label} · {punto}", med_vis),
                            use_container_width=True)
        else:
            st.info("Selecciona al menos una posición en el panel lateral.")
        st.markdown('<div class="section-title">Datos registrados</div>', unsafe_allow_html=True)
        disp = df_p.copy()
        disp["fecha"] = disp["fecha"].dt.strftime("%Y-%m-%d")
        disp.columns  = ["Fecha","Zona"]+[f"Pos {i}" for i in range(1,14)]
        st.dataframe(disp.style.background_gradient(
            cmap="RdYlGn", subset=[f"Pos {i}" for i in range(1,14)]),
            use_container_width=True, height=220)

    with tab2:
        st.markdown('<div class="section-title">Perfil de espesor a lo largo de las 13 posiciones por campaña</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_spatial(df_p, f"{unit_label} · {punto}"),
                        use_container_width=True)
        c1,c2 = st.columns(2)
        for col_st,row_data,label,color in [
            (c1,r_first,f"Primera — {df_p['fecha'].min().strftime('%Y-%m-%d')}","#42a5f5"),
            (c2,r_last, f"Última  — {df_p['fecha'].max().strftime('%Y-%m-%d')}","#ef5350"),
        ]:
            with col_st:
                st.markdown(f"**{label}**")
                vals = [row_data.get(c,np.nan) for c in m_cols]
                fb = go.Figure(go.Bar(
                    x=[str(i) for i in range(1,14)], y=vals,
                    marker_color=color,
                    hovertemplate="Pos %{x}: %{y:.3f} mm<extra></extra>",
                ))
                fb.update_layout(**BL, height=280,
                    yaxis_title="mm", xaxis_title="Posición",
                    title=dict(text=label,font_size=11))
                st.plotly_chart(fb, use_container_width=True)

    with tab3:
        st.markdown(f'<div class="section-title">Regresión — {unit_label} · {punto} · Posición {med_reg}</div>',
                    unsafe_allow_html=True)
        fig_r, forecasts = fig_regression(df_p, f"{unit_label}·{punto}",
                                           med_reg, reg_sel, threshold, forecast_yr)
        if fig_r:
            st.plotly_chart(fig_r, use_container_width=True)

        st.markdown('<div class="section-title">Mejor modelo por posición de medida</div>',
                    unsafe_allow_html=True)
        x_d,t0_d = days_from_origin(df_p.sort_values("fecha")["fecha"])
        rows_tbl = []
        for i in range(1,14):
            col = f"M{i}"
            if col not in df_p.columns: continue
            yc = df_p.sort_values("fecha")[col].values.astype(float)
            if np.any(np.isnan(yc)): continue
            best = get_all_fits(x_d, yc)[0]
            rows_tbl.append({"Posición":i,"Mejor modelo":best["name"],
                              "R²":round(best["r2"],4),"RMSE":round(best["rmse"],4),
                              "Espesor actual (mm)":round(float(df_p.sort_values("fecha")[col].iloc[-1]),3)})

        def color_r2(v):
            if v>=0.95: return "background:#1b5e20;color:#a5d6a7"
            if v>=0.80: return "background:#0d2b4e;color:#90caf9"
            return "background:#3e1e1e;color:#ef9a9a"

        if rows_tbl:
            st.dataframe(pd.DataFrame(rows_tbl).style.applymap(color_r2,subset=["R²"]),
                         use_container_width=True, height=420)

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

    with tab4:
        st.markdown('<div class="section-title">Mapa de calor — última inspección (D1–D5 × Pos 1–13)</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_heatmap(df_unit, unit_label), use_container_width=True)

        st.markdown('<div class="section-title">Desgaste acumulado total</div>',
                    unsafe_allow_html=True)
        fd = fig_delta(df_unit, unit_label)
        if fd: st.plotly_chart(fd, use_container_width=True)

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


if __name__ == "__main__":
    main()
