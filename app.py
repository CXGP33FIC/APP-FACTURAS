import streamlit as st
from jinja2 import Template
import base64
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import asyncio
import os
from playwright.async_api import async_playwright
from io import BytesIO

# Configuración de la página
st.set_page_config(page_title="Esaú Cars - Invoice Engine", page_icon="🏎️", layout="wide")

# --- MOTOR DE RENDERIZADO PLAYWRIGHT ---
async def producir_pdf(html_content):
    async with async_playwright() as p:
        # Asegurar instalación de chromium en el servidor
        os.system("playwright install chromium")
        
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Ajustar el viewport para alta definición
        await page.set_viewport_size({"width": 1280, "height": 720})
        await page.set_content(html_content, wait_until="networkidle")
        
        pdf_bytes = await page.pdf(
            format="Letter",
            print_background=True,
            margin={"top": "0cm", "bottom": "0cm", "left": "0cm", "right": "0cm"},
            display_header_footer=False,
            scale=1.0 
        )
        await browser.close()
        return pdf_bytes

# --- LÓGICA DE EXTRACCIÓN COPART ---
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

# --- INTERFAZ ---
with st.expander("🌐 Importar desde Copart", expanded=True):
    col_link, col_btn = st.columns([4, 1])
    url_input = col_link.text_input("Enlace Copart:")
    if col_btn.button("🔍 Cargar"):
        if url_input:
            with st.spinner("Extrayendo datos..."):
                n, f, e, l = extraer_datos_enlace(url_input)
                st.session_state['auto_modelo'] = n
                st.session_state['foto_extraida'] = f
                st.session_state['estado_compra'] = e
                st.session_state['lote_extraido'] = l
                st.rerun()

with st.container():
    c1, c2, c3 = st.columns(3)
    folio = c1.text_input("Folio", value="46950416")
    fecha_dt = c1.date_input("Fecha", datetime.now())
    cliente = c2.text_input("Cliente", value="Brando Gruas")
    lote = c3.text_input("Lote / ID", value=st.session_state['lote_extraido'])
    estado_v = c3.text_input("Estado", value=st.session_state['estado_compra'])
    producto = st.text_input("Vehículo (Título)", value=st.session_state['auto_modelo'])
    subir_foto = st.file_uploader("Subir foto", type=["jpg", "png"])

df_costos = st.data_editor(
    pd.DataFrame([{"Concepto": "Precio de Compra", "Monto": 0.0}]),
    num_rows="dynamic",
    use_container_width=True
)

if st.button("🚀 GENERAR PDF"):
    try:
        foto_b64 = ""
        if subir_foto:
            foto_b64 = f"data:image/png;base64,{base64.b64encode(subir_foto.read()).decode()}"
        elif st.session_state['foto_extraida']:
            img_res = requests.get(st.session_state['foto_extraida'], timeout=10)
            foto_b64 = f"data:image/png;base64,{base64.b64encode(img_res.content).decode()}"
      
        try:
            with open("logo esau cars.png", "rb") as f:
                logo_b64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except:
            logo_b64 = ""

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

        with st.spinner("Imprimiendo factura..."):
            pdf_bytes = asyncio.run(producir_pdf(html_final))
            st.success("✅ ¡Generada!")
            st.download_button("⬇️ Descargar Factura", data=pdf_bytes, file_name=f"Factura_{lote}.pdf", mime="application/pdf")
      
    except Exception as e:
        st.error(f"Error: {e}")