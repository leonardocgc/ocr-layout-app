import streamlit as st
import pdfplumber
import pandas as pd
import re
import json
import tempfile
import fitz  # PyMuPDF
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import pytesseract

def extract_text(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def extract_from_text(text, keyword, direction, only_numeric, skip_count, char_limit):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if keyword in line:
            try:
                if direction == 'lado direito':
                    data = line.split(keyword)[1].strip()
                elif direction == 'lado esquerdo':
                    data = line.split(keyword)[0].strip()
                elif direction == 'baixo':
                    data = lines[i + 1].strip()
                elif direction == 'cima' and i > 0:
                    data = lines[i - 1].strip()
                else:
                    data = ''
                if only_numeric:
                    matches = re.findall(r'\b\d[\d,.]*\b', data)
                    data = matches[skip_count] if len(matches) > skip_count else ''
                else:
                    parts = re.findall(r'\S+', data)
                    data = parts[skip_count] if len(parts) > skip_count else ''
                return data[:char_limit] if char_limit else data
            except:
                return ''
    return None

def process_pdf(file, campos, ocr_layout):
    text = extract_text(file)
    result = {"Arquivo": file.name}
    pdf_bytes = file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300, alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    for campo in campos:
        keyword, direction, only_numeric, skip_count, char_limit = campo
        result[keyword] = extract_from_text(text, keyword, direction, only_numeric, skip_count, char_limit)

    if ocr_layout:
        for ocr in ocr_layout:
            x, y, w, h = ocr["coords"]
            crop = image.crop((x, y, x + w, y + h))
            ocr_text = pytesseract.image_to_string(crop, lang="por")
            result[ocr["title"]] = ocr_text.strip()

    file.seek(0)
    return result

st.set_page_config(layout="wide")
st.title("📄 OCR com layout, prévia e marcações visuais padrão")

ocr_layout = []
drawn_shapes = []

uploaded_file = st.file_uploader("📄 PDF base", type="pdf")
layout_file = st.file_uploader("📥 Importar layout JSON", type="json")

if layout_file:
    ocr_layout = json.load(layout_file)
    st.success("Layout carregado com sucesso!")

if uploaded_file:
    # 1ª renderização visual
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    st.image(img, caption="📄 Visualização da Página")
    uploaded_file.seek(0)

    if ocr_layout:
        drawn_shapes = [{
            "type": "rect",
            "left": int(o["coords"][0]),
            "top": int(o["coords"][1]),
            "width": int(o["coords"][2]),
            "height": int(o["coords"][3]),
            "fill": "rgba(255, 165, 0, 0.3)",
            "stroke": "orange",
            "strokeWidth": 2,
            "strokeUniform": True
        } for o in ocr_layout]

    canvas = st_canvas(
        background_image=img,
        update_streamlit=True,
        height=img.height,
        width=img.width,
        drawing_mode="rect",
        fill_color="rgba(255, 165, 0, 0.3)",
        initial_drawing={"objects": drawn_shapes},
        key="canvas"
    )

    preview_layout = []
    if canvas.json_data and "objects" in canvas.json_data:
        for idx, obj in enumerate(canvas.json_data["objects"]):
            if obj["type"] == "rect":
                st.markdown(f"🟧 Marcação {idx+1}")
                coords = (int(obj["left"]), int(obj["top"]), int(obj["width"]), int(obj["height"]))
                title = st.text_input(f"Título OCR {idx+1}", value=f"OCR_{idx+1}", key=f"ocr_title_{idx}")
                crop = img.crop((coords[0], coords[1], coords[0]+coords[2], coords[1]+coords[3]))
                st.image(crop, caption=f"📍 {title}")
                ocr_text = pytesseract.image_to_string(crop, lang="por").strip()
                st.info(f"Texto OCR: {ocr_text or 'Nada reconhecido'}")
                preview_layout.append({"title": title, "coords": coords})
        ocr_layout = preview_layout
        st.download_button("⬇️ Baixar layout", data=json.dumps(ocr_layout).encode(), file_name="layout_ocr.json")

    # ⚠️ Regera a imagem para uso posterior (evita img ficar vazio)
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    if ocr_layout and (not canvas.json_data or not canvas.json_data.get("objects")):
        st.subheader("📌 Pré-visualização OCR do layout importado")
        for idx, ocr in enumerate(ocr_layout):
            x, y, w, h = ocr["coords"]
            title = ocr["title"]
            crop = img.crop((x, y, x + w, y + h))
            st.image(crop, caption=f"📍 {title}")
            ocr_text = pytesseract.image_to_string(crop, lang="por").strip()
            st.info(f"Texto OCR: {ocr_text or 'Nada reconhecido'}")

    texto = extract_text(uploaded_file)
    st.text_area("📜 Texto extraído", texto, height=250)

    campos = []
    qtd = st.number_input("Campos por palavra-chave:", 0, 10, 1)
    for i in range(qtd):
        col1, col2, col3 = st.columns(3)
        k = col1.text_input(f"Palavra-chave {i+1}", key=f"k{i}")
        d = col2.selectbox(f"Direção {i+1}", ["lado direito", "lado esquerdo", "baixo", "cima"], key=f"d{i}")
        n = col3.checkbox(f"Apenas número {i+1}", key=f"n{i}")
        s = st.number_input(f"Ignorar {i+1}", 0, 10, 0, key=f"s{i}")
        l = st.number_input(f"Limite chars {i+1}", 0, 100, 0, key=f"l{i}")
        if k:
            campos.append((k, d, n, s, l))
            resultado = extract_from_text(texto, k, d, n, s, l)
            if resultado:
                st.success(f"Valor: {resultado}")
            else:
                st.warning("Nada encontrado.")

    multi = st.file_uploader("📁 Enviar múltiplos PDFs", type="pdf", accept_multiple_files=True)
    if multi and st.button("📊 Gerar Excel"):
        resultados = [process_pdf(pdf, campos, ocr_layout) for pdf in multi]
        df = pd.DataFrame(resultados)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            df.to_excel(tmp.name, index=False)
            st.download_button("📥 Baixar Excel", open(tmp.name, "rb"), file_name="resultado_ocr.xlsx")
