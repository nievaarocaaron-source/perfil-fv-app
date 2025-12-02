import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
import os

st.set_page_config(page_title="Perfil F-V – CD Castellón", layout="wide")

with open("styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("<div class='report-title'>📊 Dashboard Perfil Fuerza–Velocidad</div>", unsafe_allow_html=True)

st.sidebar.header("Subir archivos")
cmj_file = st.sidebar.file_uploader("CMJ.csv", type="csv")
fv_file = st.sidebar.file_uploader("PERFIL FV.xlsx", type=["xlsx"])

if cmj_file and fv_file:

    cmj = pd.read_csv(cmj_file)
    fv = pd.read_excel(fv_file)

    cmj["Name_norm"] = cmj["Name"].str.strip().str.title()
    fv["Jugador_norm"] = fv["Jugador"].str.strip().str.title()

    cmj["Date_parsed"] = pd.to_datetime(cmj["Date"], dayfirst=True)
    cmj_latest = cmj.sort_values("Date_parsed").groupby("Name_norm").tail(1)

    cmj_small = cmj_latest[["Name_norm","BW [KG]","Jump Height (Imp-Mom) [cm] "]].rename(
        columns={
            "BW [KG]": "Peso_CMJ",
            "Jump Height (Imp-Mom) [cm] ": "Altura_CMJ_cm"
        }
    )

    merged = fv.merge(cmj_small, left_on="Jugador_norm", right_on="Name_norm", how="left")
    merged["Peso_final"] = merged["Peso Corporal"].fillna(merged["Peso_CMJ"])

    loads = [40,50,60,70,80,90]
    puntos = []

    for idx, row in merged.iterrows():
        nombre = row["Jugador_norm"]
        peso = row["Peso_final"]
        altura = row["Altura_CMJ_cm"]

        if pd.notna(altura):
            v_cmj = np.sqrt(2 * 9.81 * (altura/100))
            F_cmj = peso * 9.81
            puntos.append([nombre, 0, peso, F_cmj, v_cmj, "CMJ"])

        for load in loads:
            col = f"{load}kg Vmed (m/s)"
            if col in row and pd.notna(row[col]):
                total_mass = peso + load
                F = total_mass * 9.81
                puntos.append([nombre, load, total_mass, F, row[col], "HSQ"])

    puntos_df = pd.DataFrame(puntos, columns=["Jugador","Carga","Masa","Fuerza","Velocidad","Tipo"])

    resultados = []
    for nombre, sub in puntos_df.groupby("Jugador"):

        if len(sub) < 2:
            continue

        V = sub["Velocidad"].values
        F = sub["Fuerza"].values

        slope, intercept = np.polyfit(V, F, 1)
        F0 = intercept
        V0 = -intercept / slope
        Pmax = (F0 * V0) / 4
        mass = merged.loc[merged["Jugador_norm"]==nombre, "Peso_final"].iloc[0]
        F0_rel = F0 / mass

        resultados.append([nombre, F0, V0, Pmax, F0_rel])

    res_df = pd.DataFrame(resultados, columns=["Jugador","F0","V0","Pmax","F0_rel"])
    res_df = res_df.sort_values("Pmax", ascending=False)

    st.subheader("🏆 Rankings del Equipo")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("Pmax (W)")
        st.bar_chart(res_df.set_index("Jugador")["Pmax"])
    with col2:
        st.write("F0 (N)")
        st.bar_chart(res_df.set_index("Jugador")["F0"])
    with col3:
        st.write("V0 (m/s)")
        st.bar_chart(res_df.set_index("Jugador")["V0"])

    st.subheader("📌 Mapa Fuerza–Velocidad del Equipo")

    fig, ax = plt.subplots(figsize=(6,4))
    ax.scatter(res_df["V0"], res_df["F0"], s=70, color="#007bff")
    for i, row in res_df.iterrows():
        ax.text(row["V0"]+0.02, row["F0"]+5, row["Jugador"], fontsize=8)
    ax.set_xlabel("V0 (m/s)")
    ax.set_ylabel("F0 (N)")
    st.pyplot(fig)

    st.subheader("👤 Perfil F-V Individual")

    jugador_sel = st.selectbox("Seleccionar jugador", res_df["Jugador"].unique())
    sub = puntos_df[puntos_df["Jugador"] == jugador_sel]
    V = sub["Velocidad"].values
    F = sub["Fuerza"].values

    fig_i, ax_i = plt.subplots(figsize=(6,4))
    ax_i.scatter(V, F, s=60, color="#007bff")

    if len(V) > 1:
        slope, intercept = np.polyfit(V, F, 1)
        V_line = np.linspace(min(V), max(V), 50)
        F_line = slope * V_line + intercept
        ax_i.plot(V_line, F_line, color="red", linewidth=2)

    ax_i.set_xlabel("Velocidad (m/s)")
    ax_i.set_ylabel("Fuerza (N)")
    ax_i.set_title(f"Perfil F-V - {jugador_sel}")
    st.pyplot(fig_i)

    st.subheader("📄 Exportar PDF individual")

    if st.button("Descargar PDF del jugador"):

        fig_i.savefig("grafica_fv.png", dpi=120)
        plt.close(fig_i)

        pos_p = res_df.sort_values("Pmax", ascending=False).reset_index(drop=True)
        rank_p = pos_p.index[pos_p["Jugador"]==jugador_sel][0] + 1

        pos_f = res_df.sort_values("F0", ascending=False).reset_index(drop=True)
        rank_f = pos_f.index[pos_f["Jugador"]==jugador_sel][0] + 1

        row = res_df[res_df["Jugador"]==jugador_sel].iloc[0]

        F0_val = row["F0"]
        V0_val = row["V0"]

        if V0_val > 4.5 and F0_val < 1800:
            interpret = "Perfil orientado a VELOCIDAD (déficit de fuerza máxima)."
        elif F0_val > 2300 and V0_val < 3.5:
            interpret = "Perfil orientado a FUERZA (déficit de velocidad)."
        else:
            interpret = "Perfil equilibrado."

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        if os.path.exists("logo.png"):
            pdf.image("logo.png", x=10, y=8, w=30)

        pdf.set_font("Arial", "B", 18)
        title = f"Informe F-V – {jugador_sel}"
        pdf.cell(0, 15, title.encode("latin-1","replace").decode("latin-1"), ln=1)

        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Ranking Pmax: {rank_p}/{len(res_df)}", ln=1)
        pdf.cell(0, 10, f"Ranking F0: {rank_f}/{len(res_df)}", ln=1)

        pdf.ln(5)

        for t in [
            f"F0: {row['F0']:.2f} N",
            f"V0: {row['V0']:.2f} m/s",
            f"Pmax: {row['Pmax']:.2f} W",
        ]:
            pdf.cell(0, 8, t.encode("latin-1","replace").decode("latin-1"), ln=1)

        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Interpretación:", ln=1)

        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 7, interpret.encode("latin-1","replace").decode("latin-1"))

        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Gráfica Perfil F-V:", ln=1)
        pdf.image("grafica_fv.png", w=150)

        pdf.output("perfil_jugador.pdf")

        with open("perfil_jugador.pdf","rb") as f:
            st.download_button("Descargar PDF", f, file_name=f"Perfil_{jugador_sel}.pdf")
