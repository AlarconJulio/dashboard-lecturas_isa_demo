import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client

# ── CONFIG ──────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://ydubhmvafhvdqwotynvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlkdWJobXZhZmh2ZHF3b3R5bnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2NDY0NTIsImV4cCI6MjA5MDIyMjQ1Mn0.nD9XbnaY_DXVCYXqyYh0MPY6HM3bq_QblHddT_c1EC8"

st.set_page_config(
    page_title="Dashboard Lecturas Motorizadas",
    page_icon="⚡",
    layout="wide",
)

# ── CARGA DE DATOS ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def cargar_datos():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    todos = []
    lote = 1000
    offset = 0
    while True:
        res = sb.table("registros_lectura").select("*").range(offset, offset + lote - 1).execute()
        todos.extend(res.data)
        if len(res.data) < lote:
            break
        offset += lote
    df = pd.DataFrame(todos)
    if df.empty:
        return df
    df["fecha_trabajo"] = pd.to_datetime(df["fecha_trabajo"], format="%d/%m/%Y", errors="coerce")
    return df

df = cargar_datos()

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Lightning_bolt.svg/64px-Lightning_bolt.svg.png", width=40)
st.sidebar.title("Filtros")

if not df.empty:
    fechas = df["fecha_trabajo"].dropna().sort_values()
    fecha_min, fecha_max = fechas.min().date(), fechas.max().date()
    rango = st.sidebar.date_input("Rango de fechas", value=(fecha_min, fecha_max), min_value=fecha_min, max_value=fecha_max)

    sectores = ["Todos"] + sorted(df["sector"].dropna().unique().tolist())
    sector_sel = st.sidebar.selectbox("Sector", sectores)

    tipo_opts = ["Todos"] + sorted(df["tipo_lectura"].dropna().unique().tolist())
    tipo_sel = st.sidebar.selectbox("Tipo de lectura", tipo_opts)

    # Aplicar filtros
    mask = (df["fecha_trabajo"].dt.date >= rango[0]) & (df["fecha_trabajo"].dt.date <= rango[1])
    dff = df[mask].copy()
    if sector_sel != "Todos":
        dff = dff[dff["sector"] == sector_sel]
    if tipo_sel != "Todos":
        dff = dff[dff["tipo_lectura"] == tipo_sel]
else:
    dff = df

if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["Resumen", "Lectores", "Anomalías", "Detalle"])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN EJECUTIVO
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Resumen ejecutivo")

    if dff.empty:
        st.warning("Sin datos para el rango seleccionado.")
    else:
        total = len(dff)
        conformes = (dff["tipo_lectura"] == "conforme").sum()
        noconformes = (dff["tipo_lectura"] == "noconforme").sum()
        ok = (dff["verificacion_final"] == "OK").sum()
        nok = (dff["verificacion_final"] == "NOK (continuó sin validar)").sum()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total SEDs", total)
        c2.metric("Conformes", conformes)
        c3.metric("No conformes", noconformes)
        c4.metric("Verificación OK", ok)
        c5.metric("Verificación NOK", nok)

        st.divider()

        # Avance diario
        st.subheader("Avance diario")
        avance = dff.groupby(["fecha_trabajo", "tipo_lectura"]).size().reset_index(name="cantidad")
        avance["fecha_trabajo"] = avance["fecha_trabajo"].dt.strftime("%d/%m")
        fig = px.bar(
            avance, x="fecha_trabajo", y="cantidad", color="tipo_lectura",
            color_discrete_map={"conforme": "#2ecc71", "noconforme": "#e74c3c", "confirmar_sed_sector": "#f39c12"},
            labels={"fecha_trabajo": "Fecha", "cantidad": "Registros", "tipo_lectura": "Tipo"},
            barmode="stack",
        )
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Conforme vs No conforme")
            pie1 = dff["tipo_lectura"].value_counts().reset_index()
            pie1.columns = ["tipo", "cantidad"]
            fig2 = px.pie(pie1, names="tipo", values="cantidad",
                          color_discrete_sequence=["#2ecc71", "#e74c3c", "#f39c12"])
            st.plotly_chart(fig2, use_container_width=True)

        with col2:
            st.subheader("Verificación final")
            pie2 = dff["verificacion_final"].value_counts().reset_index()
            pie2.columns = ["estado", "cantidad"]
            fig3 = px.pie(pie2, names="estado", values="cantidad",
                          color_discrete_sequence=["#3498db", "#e74c3c", "#95a5a6"])
            st.plotly_chart(fig3, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — PRODUCTIVIDAD POR LECTOR
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Productividad por lector")

    if dff.empty:
        st.warning("Sin datos.")
    else:
        prod = dff.groupby(["user_id", "tipo_lectura"]).size().unstack(fill_value=0).reset_index()
        prod.columns.name = None
        for col in ["conforme", "noconforme", "confirmar_sed_sector"]:
            if col not in prod.columns:
                prod[col] = 0
        prod["total"] = prod["conforme"] + prod["noconforme"] + prod.get("confirmar_sed_sector", 0)
        prod = prod.sort_values("total", ascending=False)
        prod["user_id"] = prod["user_id"].astype(str)

        fig4 = px.bar(
            prod, x="user_id", y=["conforme", "noconforme"],
            color_discrete_map={"conforme": "#2ecc71", "noconforme": "#e74c3c"},
            labels={"user_id": "Lector (ID)", "value": "Registros", "variable": "Tipo"},
            barmode="stack",
            title="Registros por lector"
        )
        st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Tabla detalle por lector")
        prod["user_id"] = prod["user_id"].astype(str)
        st.dataframe(prod[["user_id", "conforme", "noconforme", "total"]].rename(columns={
            "user_id": "Lector (ID)", "conforme": "Conformes", "noconforme": "No conformes", "total": "Total"
        }), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — ANOMALÍAS
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Análisis de anomalías")

    if dff.empty:
        st.warning("Sin datos.")
    else:
        nc = dff[dff["tipo_lectura"] == "noconforme"].copy()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Anomalías primarias")
            ap = nc["anomalia_primaria"].value_counts().reset_index()
            ap.columns = ["anomalia", "cantidad"]
            fig5 = px.bar(ap, x="cantidad", y="anomalia", orientation="h",
                          color_discrete_sequence=["#e67e22"])
            fig5.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig5, use_container_width=True)

        with col2:
            st.subheader("Anomalías secundarias")
            ase = nc["anomalia_secundaria"].value_counts().reset_index()
            ase.columns = ["anomalia", "cantidad"]
            fig6 = px.bar(ase, x="cantidad", y="anomalia", orientation="h",
                          color_discrete_sequence=["#c0392b"])
            fig6.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig6, use_container_width=True)

        st.subheader("Anomalías por sector")
        if not nc.empty:
            heat = nc.groupby(["sector", "anomalia_primaria"]).size().reset_index(name="cantidad")
            fig7 = px.density_heatmap(
                heat, x="sector", y="anomalia_primaria", z="cantidad",
                color_continuous_scale="Reds",
                labels={"sector": "Sector", "anomalia_primaria": "Anomalía", "cantidad": "Casos"}
            )
            fig7.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig7, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — DETALLE
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Detalle de registros")

    if dff.empty:
        st.warning("Sin datos.")
    else:
        buscar = st.text_input("Buscar por SED o num. medidor")
        mostrar = dff.copy()
        mostrar["fecha_trabajo"] = mostrar["fecha_trabajo"].dt.strftime("%d/%m/%Y")

        if buscar:
            mask2 = (
                mostrar["sed"].astype(str).str.contains(buscar, case=False, na=False) |
                mostrar["num_medidor"].astype(str).str.contains(buscar, case=False, na=False)
            )
            mostrar = mostrar[mask2]

        cols_show = ["sed", "sector", "tipo_lectura", "fecha_trabajo", "user_id",
                     "anomalia_primaria", "anomalia_secundaria", "verificacion_final", "observaciones"]
        st.dataframe(mostrar[cols_show].reset_index(drop=True), use_container_width=True, height=500)
        st.caption(f"{len(mostrar)} registros mostrados")
