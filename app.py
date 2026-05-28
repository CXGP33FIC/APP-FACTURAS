import streamlit as st
from jinja2 import Template
import base64
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import os
from xhtml2pdf import pisa
from io import BytesIO

st.set_page_config(page_title="Esaú Cars - Invoice Engine", page_icon="🏎️", layout="wide")

def extraer_datos_enlace(url):
   try:
       headers = {"User-Agent": "Mozilla/5.0"}
       response = requests.get(url, headers=headers, timeout=15)
       soup = BeautifulSoup(response.text, 'html.parser')
       meta_title = soup.find("meta", property="og:title")
       nombre_raw = meta_title["content"].split('|')[0].replace("Copart", "").strip() if meta_title else ""
       nombre_final = " ".join(nombre_raw.split()).upper()
       meta_img = soup.find("meta", property="og:image")
       foto_url = meta_img["content"] if meta_img else None
       lote_match = re.search(r'/lot/(\d+)', url)
       lote_ext = lote_match.group(1) if lote_match else ""
       return nombre_final, foto_url, lote_ext
   except:
       return "", None, ""

for key in ['auto_modelo', 'foto_extraida', 'lote_extraido']:
   if key not in st.session_state: st.session_state[key] = ""

st.title("🏎️ ESAÚ CARS | Generador de Facturas")

with st.expander("🌐 Importar desde Copart", expanded=True):
   url_input = st.text_input("Pega el enlace aquí:")
   if st.button("🔍 Cargar Datos"):
       n, f, l = extraer_datos_enlace(url_input)
       st.session_state['auto_modelo'], st.session_state['foto_extraida'], st.session_state['lote_extraido'] = n, f, l
       st.rerun()

c1, c2 = st.columns(2)
folio = c1.text_input("Folio", value="46950416")
cliente = c2.text_input("Cliente", value="Brando Gruas")
lote = c1.text_input("Lote / ID", value=st.session_state['lote_extraido'])
producto = st.text_input("Vehículo", value=st.session_state['auto_modelo'])
subir_foto = st.file_uploader("Cambiar foto", type=["jpg", "png"])

df_costos = st.data_editor(pd.DataFrame([{"Concepto": "Precio de Compra", "Monto": 0.0}]), num_rows="dynamic", use_container_width=True)

if st.button("🚀 GENERAR PDF"):
    try:
        foto_b64 = ""
        if subir_foto:
            foto_b64 = f"data:image/png;base64,{base64.b64encode(subir_foto.read()).decode()}"
        elif st.session_state['foto_extraida']:
            img_res = requests.get(st.session_state['foto_extraida'])
            foto_b64 = f"data:image/png;base64,{base64.b64encode(img_res.content).decode()}"
      
        with open("logo esau cars.png", "rb") as f:
            logo_b64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
      
        with open("plantilla.html", "r", encoding="utf-8") as f:
            template = Template(f.read())

        html_final = template.render(
            producto=producto.upper(), cliente=cliente.upper(), fecha=datetime.now().strftime("%d/%m/%Y"),
            lote=lote, foto_url=foto_b64, logo_url=logo_b64,
            costos=df_costos.to_dict('records'), total=f"{df_costos['Monto'].sum():,.2f}"
        )

        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html_final.encode("UTF-8")), result)
        
        if not pdf.err:
            st.success("✅ ¡Factura generada!")
            st.download_button("⬇️ Descargar", data=result.getvalue(), file_name=f"Factura_{lote}.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"Error: {e}")