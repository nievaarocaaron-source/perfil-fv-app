import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
import os

st.set_page_config(page_title="Perfil F-V – CD Castellón", layout="wide")

# Cargar estilos si existen
try:
    with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

st.markdown("<div class='report-title'>📊 Dashboard Perfil Fuerza–Velocidad</div>", unsafe_allow_html=True)

# Sidebar: subida de archivos
st.sidebar.header("Subir archivos")
cmj_file = st.sidebar.file_uploader("CMJ.csv", type="csv")
fv_file = st.sidebar.file_uploader("PERFIL FV.xlsx", type=["xlsx"])

if cmj_file and fv_file:

    # ----------------------------
    # 1. LECTURA Y PREPROCESADO
    # ----------------------------
    cmj = pd.read_csv(cmj_file)
    fv = pd.read_excel(fv_file)

    # Normalizar nombres
    cmj["Name_norm"] = cmj["Name"].astype(str).str.strip().str.title()
    fv["Jugador_norm"] = fv["Jugador"].astype(str).str.strip().str.title()

    # Tomar último CMJ por jugador
    cmj["Date_parsed"] = pd.to_datetime(cmj["Date"], dayfirst=True, errors="coerce")
    cmj_latest = cmj.sort_values("Date_parsed").groupby("Name_norm").tail(1)

    cmj_small = cmj_latest[[
        "Name_norm",
        "BW [KG]",
        "Jump Height (Imp-Mom) [cm] "
    ]].rename(columns={
        "BW [KG]": "Peso_CMJ",
        "Jump Height (Imp-Mom) [cm] ": "Altura_CMJ_cm"
    })

    # Unir FV con CMJ
    merged = fv.merge(cmj_small, left_on="Jugador_norm", right_on="Name_norm", how="left")

    # Peso final (prioridad a peso de FV si está)
    merged["Peso_final"] = merged["Peso Corporal"].fillna(merged["Peso_CMJ"])

    # ---------------------------------
    # 2. CONSTRUIR PUNTOS F-V (HSQ+CMJ)
    # ---------------------------------
    loads = [40, 50, 60, 70, 80, 90]
    puntos = []  # lista: [Jugador, Carga, Masa, Fuerza, Velocidad, Tipo]

    for idx, row in merged.iterrows():
        nombre = row["Jugador_norm"]
        peso = row["Peso_final"]
        altura = row.get("Altura_CMJ_cm", np.nan)

        # Punto CMJ
        if pd.notna(altura) and pd.notna(peso):
            v_cmj = np.sqrt(2 * 9.81 * (altura / 100.0))
            F_cmj = peso * 9.81
            puntos.append([nombre, 0.0, float(peso), float(F_cmj), float(v_cmj), "CMJ"])

        # Puntos sentadilla con cargas
        for load in loads:
            col = f"{load}kg Vmed (m/s)"
            if col in merged.columns and pd.notna(row.get(col, np.nan)) and pd.notna(peso):
                total_mass = peso + load
                F = total_mass * 9.81
                puntos.append([nombre, float(load), float(total_mass), float(F), float(row[col]), "HSQ"])

    if len(puntos) == 0:
        st.error("No se han podido generar puntos F-V. Revisa que el Excel tenga columnas de velocidad (40–90 kg).")
        st.stop()

    puntos_df = pd.DataFrame(puntos, columns=["Jugador", "Carga", "Masa", "Fuerza", "Velocidad", "Tipo"])

    # ----------------------------
    # 3. CMJ: métricas y ranking
    # ----------------------------
    cmj_metrics = []
    for idx, row in merged.iterrows():
        nombre = row["Jugador_norm"]
        altura = row.get("Altura_CMJ_cm", np.nan)
        peso = row.get("Peso_final", np.nan)
        if pd.notna(altura) and pd.notna(peso):
            v_cmj = np.sqrt(2 * 9.81 * (altura / 100.0))
            F_cmj = peso * 9.81
            P_cmj = F_cmj * v_cmj
            cmj_metrics.append([nombre, altura, v_cmj, P_cmj])

    cmj_df = pd.DataFrame(cmj_metrics, columns=["Jugador", "Altura_CMJ_cm", "V_CMJ", "P_CMJ"])
    cmj_df = cmj_df.drop_duplicates(subset=["Jugador"])

    # Ranking CMJ (por altura)
    if not cmj_df.empty:
        cmj_rank = cmj_df.sort_values("Altura_CMJ_cm", ascending=False).reset_index(drop=True)
        cmj_rank["Rank_CMJ"] = cmj_rank.index + 1
    else:
        cmj_rank = pd.DataFrame(columns=["Jugador", "Altura_CMJ_cm", "V_CMJ", "P_CMJ", "Rank_CMJ"])

    # -------------------------------------
    # 4. PERFIL F-V: F0, V0, Pmax, F_rel
    # -------------------------------------
    resultados = []
    for nombre, sub in puntos_df.groupby("Jugador"):

        if len(sub) < 2:
            continue

        V = sub["Velocidad"].values
        Fv = sub["Fuerza"].values

        # Recta F-V
        slope, intercept = np.polyfit(V, Fv, 1)
        F0 = intercept
        V0 = -intercept / slope
        Pmax = (F0 * V0) / 4

        mass_series = merged.loc[merged["Jugador_norm"] == nombre, "Peso_final"]
        mass = mass_series.iloc[0] if not mass_series.empty else np.nan
        F0_rel = F0 / mass if mass and not np.isnan(mass) else np.nan

        resultados.append([nombre, F0, V0, Pmax, F0_rel])

    if len(resultados) == 0:
        st.error("No se han podido ajustar perfiles F-V. Revisa que haya al menos dos puntos por jugador.")
        st.stop()

    res_df = pd.DataFrame(resultados, columns=["Jugador", "F0", "V0", "Pmax", "F0_rel"])
    res_df = res_df.drop_duplicates(subset=["Jugador"])
    res_df = res_df.sort_values("Pmax", ascending=False)

    # ----------------------------
    # 5. DASHBOARD GLOBAL
    # ----------------------------
    st.subheader("🏆 Rankings del equipo")

    # Unir F-V + CMJ para rankings
    res_with_cmj = res_df.merge(cmj_df[["Jugador", "Altura_CMJ_cm"]], on="Jugador", how="left")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.write("Pmax (W)")
        st.bar_chart(res_with_cmj.set_index("Jugador")["Pmax"])
    with col2:
        st.write("F0 (N)")
        st.bar_chart(res_with_cmj.set_index("Jugador")["F0"])
    with col3:
        st.write("V0 (m/s)")
        st.bar_chart(res_with_cmj.set_index("Jugador")["V0"])
    with col4:
        if "Altura_CMJ_cm" in res_with_cmj.columns and not res_with_cmj["Altura_CMJ_cm"].isna().all():
            st.write("CMJ (cm)")
            st.bar_chart(res_with_cmj.set_index("Jugador")["Altura_CMJ_cm"])
        else:
            st.write("CMJ (cm)")
            st.info("Sin datos de CMJ válidos.")

    # Scatter F-V global
    st.subheader("📌 Mapa Fuerza–Velocidad del equipo")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(res_df["V0"], res_df["F0"], s=70, color="#007bff")
    for i, row in res_df.iterrows():
        ax.text(row["V0"] + 0.02, row["F0"] + 5, row["Jugador"], fontsize=8)
    ax.set_xlabel("V0 (m/s)")
    ax.set_ylabel("F0 (N)")
    st.pyplot(fig)

    # ----------------------------
    # 6. PERFIL INDIVIDUAL + CMJ
    # ----------------------------
    st.subheader("👤 Perfil F-V y CMJ individual")

    jugador_sel = st.selectbox("Seleccionar jugador", res_df["Jugador"].unique())

    # Puntos del jugador
    sub_j = puntos_df[puntos_df["Jugador"] == jugador_sel]
    Vj = sub_j["Velocidad"].values
    Fj = sub_j["Fuerza"].values

    # CMJ de ese jugador (si existe)
    cmj_row = cmj_df[cmj_df["Jugador"] == jugador_sel]
    has_cmj = not cmj_row.empty

    # Gráfica individual con CMJ
    fig_i, ax_i = plt.subplots(figsize=(6, 4))
    ax_i.scatter(Vj, Fj, s=60, color="#007bff", label="HSQ / puntos F-V")

    if len(Vj) > 1:
        slope_j, intercept_j = np.polyfit(Vj, Fj, 1)
        V_line = np.linspace(min(Vj), max(Vj), 50)
        F_line = slope_j * V_line + intercept_j
        ax_i.plot(V_line, F_line, color="red", linewidth=2, label="Recta F-V")
    else:
        slope_j, intercept_j = None, None

    # Punto CMJ diferenciado
    if has_cmj:
        altura_c = cmj_row["Altura_CMJ_cm"].iloc[0]
        v_cmj = cmj_row["V_CMJ"].iloc[0]
        mass_series_j = merged.loc[merged["Jugador_norm"] == jugador_sel, "Peso_final"]
        mass_j = mass_series_j.iloc[0] if not mass_series_j.empty else np.nan
        F_cmj = mass_j * 9.81 if pd.notna(mass_j) else np.nan
        if pd.notna(F_cmj):
            ax_i.scatter([v_cmj], [F_cmj], color="gold", edgecolor="black", s=90, zorder=5, label="CMJ")

    ax_i.set_xlabel("Velocidad (m/s)")
    ax_i.set_ylabel("Fuerza (N)")
    ax_i.set_title(f"Perfil F-V - {jugador_sel}")
    ax_i.legend(loc="best")
    st.pyplot(fig_i)

    # Bloque datos CMJ
    st.markdown("#### 📏 Datos de CMJ del jugador")
    if has_cmj:
        altura = cmj_row["Altura_CMJ_cm"].iloc[0]
        v_cmj = cmj_row["V_CMJ"].iloc[0]
        p_cmj = cmj_row["P_CMJ"].iloc[0]

        # Percentil dentro del equipo
        if not cmj_rank.empty and jugador_sel in list(cmj_rank["Jugador"]):
            rank_row = cmj_rank[cmj_rank["Jugador"] == jugador_sel].iloc[0]
            rank_pos = int(rank_row["Rank_CMJ"])
            total = len(cmj_rank)
            texto_rank = f"CMJ: posición {rank_pos}/{total} del equipo"
        else:
            texto_rank = "CMJ: sin ranking disponible"

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Altura CMJ (cm)", f"{altura:.1f}")
        with col_b:
            st.metric("Velocidad despegue (m/s)", f"{v_cmj:.2f}")
        with col_c:
            st.metric("Potencia estimada (W)", f"{p_cmj:.0f}")

        st.caption(texto_rank)
    else:
        st.info("Este jugador no tiene un CMJ válido registrado en el CSV.")

    # ----------------------------
    # 7. EXPORTAR PDF INDIVIDUAL
    # ----------------------------
    st.subheader("📄 Exportar PDF individual")

    if st.button("Descargar PDF del jugador"):

        # Guardar gráfica individual
        fig_i.savefig("grafica_fv.png", dpi=120)
        plt.close(fig_i)

        # Ranking F-V
        pos_p = res_df.sort_values("Pmax", ascending=False).reset_index(drop=True)
        rank_p = pos_p.index[pos_p["Jugador"] == jugador_sel][0] + 1

        pos_f = res_df.sort_values("F0", ascending=False).reset_index(drop=True)
        rank_f = pos_f.index[pos_f["Jugador"] == jugador_sel][0] + 1

        row_fv = res_df[res_df["Jugador"] == jugador_sel].iloc[0]

        F0_val = row_fv["F0"]
        V0_val = row_fv["V0"]

        # Interpretación según F-V
        if V0_val > 4.5 and F0_val < 1800:
            interpret = "Perfil orientado a VELOCIDAD (déficit de fuerza máxima)."
        elif F0_val > 2300 and V0_val < 3.5:
            interpret = "Perfil orientado a FUERZA (déficit de velocidad)."
        else:
            interpret = "Perfil equilibrado."

        # Datos CMJ para PDF
        altura_txt = ""
        vcmj_txt = ""
        pcmj_txt = ""
        if has_cmj:
            altura = cmj_row["Altura_CMJ_cm"].iloc[0]
            v_cmj = cmj_row["V_CMJ"].iloc[0]
            p_cmj = cmj_row["P_CMJ"].iloc[0]
            altura_txt = f"Altura CMJ: {altura:.1f} cm"
            vcmj_txt = f"Velocidad despegue CMJ: {v_cmj:.2f} m/s"
            pcmj_txt = f"Potencia CMJ estimada: {p_cmj:.0f} W"

        # Crear PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Logo si existe
        if os.path.exists("logo.png"):
            try:
                pdf.image("logo.png", x=10, y=8, w=30)
            except Exception:
                pass

        pdf.set_font("Arial", "B", 18)
        title = f"Informe F-V - {jugador_sel}"
        pdf.cell(0, 15, title.encode("latin-1", "replace").decode("latin-1"), ln=1)

        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"Ranking Pmax: {rank_p}/{len(res_df)}", ln=1)
        pdf.cell(0, 8, f"Ranking F0: {rank_f}/{len(res_df)}", ln=1)

        pdf.ln(4)
        for t in [
            f"F0: {row_fv['F0']:.2f} N",
            f"V0: {row_fv['V0']:.2f} m/s",
            f"Pmax: {row_fv['Pmax']:.2f} W",
        ]:
            pdf.cell(0, 8, t.encode("latin-1", "replace").decode("latin-1"), ln=1)

        if altura_txt:
            pdf.ln(4)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, "Datos de CMJ:", ln=1)
            pdf.set_font("Arial", size=11)
            for t in [altura_txt, vcmj_txt, pcmj_txt]:
                pdf.cell(0, 7, t.encode("latin-1", "replace").decode("latin-1"), ln=1)

        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Interpretación F-V:", ln=1)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 7, interpret.encode("latin-1", "replace").decode("latin-1"))

        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Gráfica Perfil F-V:", ln=1)
        if os.path.exists("grafica_fv.png"):
            try:
                pdf.image("grafica_fv.png", w=150)
            except Exception:
                pass

        pdf.output("perfil_jugador.pdf")

        with open("perfil_jugador.pdf","rb") as f:
            st.download_button("Descargar PDF", f, file_name=f"Perfil_{jugador_sel}.pdf")
