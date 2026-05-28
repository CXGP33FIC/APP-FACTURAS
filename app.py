import streamlit as st
from jinja2 import Template
import pdfkit
import base64
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import os  # NUEVO: Para detectar el sistema operativo

# Configuración de la página
st.set_page_config(page_title="Esaú Cars - Invoice Engine", page_icon="🏎️", layout="wide")

# --- LÓGICA DE EXTRACCIÓN ---
def extraer_datos_enlace(url):
   try:
       headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
       response = requests.get(url, headers=headers, timeout=15)
       soup = BeautifulSoup(response.text, 'html.parser')
      
       meta_title = soup.find("meta", property="og:title")
       nombre_raw = meta_title["content"].split('|')[0].replace("Copart", "").strip() if meta_title else ""
      
       if not nombre_raw or "Online" in nombre_raw:
           url_slug = url.split('/')[-1] if url.split('/')[-1] else url.split('/')[-2]
           nombre_raw = url_slug.replace('-', ' ')

       patron_corte = r'\s(TX|CA|FL|AZ|NY|IL|GA|PA|NC|OH|NJ|VA|WA|MA|CO|MD)\s'
       nombre_limpio = re.split(patron_corte, nombre_raw, flags=re.IGNORECASE)[0]
      
       palabras_basura = ["CLEAN TITLE", "SALVAGE TITLE", "CERTIFICATE OF TITLE", "NON-REPAIRABLE", "ONLINE INVENTORY", "AUCTION"]
       for palabra in palabras_basura:
           nombre_limpio = re.sub(rf'\b{palabra}\b', '', nombre_limpio, flags=re.IGNORECASE)

       nombre_final = " ".join(nombre_limpio.split()).upper()

       meta_img = soup.find("meta", property="og:image")
       foto_url = meta_img["content"] if meta_img else None
      
       estado_v = ""
       estados_map = {'tx': 'TEXAS', 'ca': 'CALIFORNIA', 'fl': 'FLORIDA', 'az': 'ARIZONA'}
       for abr, nombre_full in estados_map.items():
           if f"-{abr}-" in url.lower():
               estado_v = nombre_full
               break
      
       lote_match = re.search(r'/lot/(\d+)', url) or re.search(r'lotId=(\d+)', url)
       lote_ext = lote_match.group(1) if lote_match else ""
              
       return nombre_final, foto_url, estado_v, lote_ext
   except:
       return "", None, "", ""

# --- MANEJO DE SESIÓN ---
for key in ['auto_modelo', 'foto_extraida', 'estado_compra', 'lote_extraido']:
   if key not in st.session_state:
       st.session_state[key] = ""

st.title("🏎️ ESAÚ CARS | Generador de Facturas")

# --- SECCIÓN DE IMPORTACIÓN ---
with st.expander("🌐 Importar desde Copart", expanded=True):
   col_link, col_btn = st.columns([4, 1])
   url_input = col_link.text_input("Pega el enlace aquí:")
   if col_btn.button("🔍 Cargar Datos"):
       if url_input:
           with st.spinner("Limpiando y extrayendo datos e imagen..."):
               n, f, e, l = extraer_datos_enlace(url_input)
               st.session_state['auto_modelo'] = n
               st.session_state['foto_extraida'] = f
               st.session_state['estado_compra'] = e
               st.session_state['lote_extraido'] = l
               st.rerun()

# --- FORMULARIO ---
with st.container():
   c1, c2, c3 = st.columns(3)
   folio = c1.text_input("Folio", value="46950416")
   fecha_dt = c1.date_input("Fecha", datetime.now())
  
   cliente = c2.text_input("Cliente", value="Brando Gruas")
   tel = c2.text_input("Teléfono", value="663 103 1285")
  
   lote = c3.text_input("Lote / ID", value=st.session_state['lote_extraido'])
   estado_v = c3.text_input("Estado", value=st.session_state['estado_compra'])

   producto = st.text_input("Vehículo", value=st.session_state['auto_modelo'])
  
   subir_foto = st.file_uploader("Cambiar foto (Opcional)", type=["jpg", "png"])
   if st.session_state['foto_extraida'] and not subir_foto:
       st.info("✅ Imagen detectada automáticamente del enlace.")

df_costos = st.data_editor(
   pd.DataFrame([{"Concepto": "Precio de Compra", "Monto": 0.0}]),
   num_rows="dynamic",
   use_container_width=True
)

# --- BOTÓN GENERAR ---
if st.button("🚀 GENERAR PDF"):
   try:
       foto_b64 = ""
       if subir_foto:
           foto_b64 = f"data:image/png;base64,{base64.b64encode(subir_foto.read()).decode()}"
       elif st.session_state['foto_extraida']:
           try:
               img_res = requests.get(st.session_state['foto_extraida'], timeout=10)
               foto_b64 = f"data:image/png;base64,{base64.b64encode(img_res.content).decode()}"
           except:
               foto_b64 = ""
      
       with open("logo esau cars.png", "rb") as f:
           logo_b64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
      
       with open("plantilla.html", "r", encoding="utf-8") as f:
           template = Template(f.read())

       fecha_str = fecha_dt.strftime("%d/%m/%Y")
       html_final = template.render(
           producto=producto.upper(),
           estado=estado_v.upper(),
           cliente=cliente.upper(),
           fecha=fecha_str,
           lote=lote,
           foto_url=foto_b64,
           logo_url=logo_b64,
           costos=df_costos.to_dict('records'),
           total=f"{df_costos['Monto'].sum():,.2f}"
       )

       # CONFIGURACIÓN INTELIGENTE SEGÚN EL SISTEMA
       if os.name == 'nt':  # Si es Windows
           path_wk = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe' # Ajusta si tu ruta es distinta
           config = pdfkit.configuration(wkhtmltopdf=path_wk)
       else:  # Si es Linux (Streamlit Cloud)
           config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')

       options = {
           'page-size': 'Letter',
           'encoding': "UTF-8",
           'margin-top': '0',
           'margin-bottom': '0',
           'margin-left': '0',
           'margin-right': '0',
           'enable-local-file-access': None
       }
       
       pdf = pdfkit.from_string(html_final, False, configuration=config, options=options)
      
       st.success("✅ ¡Factura generada!")
       st.download_button("⬇️ Descargar Factura", data=pdf, file_name=f"Factura_{lote}.pdf", mime="application/pdf")
      
   except Exception as e:
       st.error(f"Error: {e}")