from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import requests
import os
import re
import tempfile
import urllib3
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import create_engine
import fitz  # PyMuPDF

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="API de Similitud Moodle", version="2.1.0")

# Configuración Moodle
MOODLE_URL = "https://campusvirtual-sifods.minedu.gob.pe"
MOODLE_APIKEY = "365d5e601bd29d6e983e643c513dfb0d"
MOODLE_USERNAME = "70321563"
MOODLE_PASSWORD = "70321563"

# Configuración Base de Datos (ajustar según entorno)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "proyectos_ia")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")

class ConsultaSimilitudRequest(BaseModel):
    course_id: int
    cmid: int
    user_id: int
    top_k: int = 5
    threshold: float = 0.75  # Umbral de similitud mínimo

# ----------------------------------------------------------------------
# Funciones de base de datos
# ----------------------------------------------------------------------
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def limpiar_texto_avanzado(texto: str) -> str:
    """Limpieza avanzada de texto manejando diferentes codificaciones."""
    if not texto:
        return ""
    
    # Si es bytes, decodificar
    if isinstance(texto, bytes):
        try:
            texto = texto.decode('utf-8', errors='ignore')
        except:
            try:
                texto = texto.decode('latin-1', errors='ignore')
            except:
                texto = texto.decode('ascii', errors='ignore')
    
    # Asegurar que es string
    texto = str(texto)
    
    # Eliminar caracteres de control excepto saltos de línea y tabs
    texto = ''.join(char for char in texto if ord(char) >= 32 or char in '\n\r\t')
    
    # Normalizar espacios
    texto = re.sub(r'\s+', ' ', texto)
    
    # Convertir a minúsculas y eliminar caracteres especiales
    texto = texto.lower()
    texto = re.sub(r'[^\w\sáéíóúüñ]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    
    return texto.strip()

def limpiar_texto(texto: str) -> str:
    """Wrapper para limpiar_texto_avanzado."""
    return limpiar_texto_avanzado(texto)

def guardar_documento(course_id, cmid, submission_id, assign_id, user_id,
                      timecreated, timemodified, filename, fileurl, texto):
    """
    Inserta o actualiza un documento. Convierte los timestamps enteros a datetime.
    """
    # Asegurar que el texto sea válido UTF-8
    if isinstance(texto, bytes):
        texto = texto.decode('utf-8', errors='ignore')
    texto = str(texto)
    
    texto_limpio = limpiar_texto(texto)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verificar si existe el submission_id y obtener su timemodified (datetime)
            cur.execute("""
                SELECT timemodified FROM documentos_similitud
                WHERE moodle_submission_id = %s
            """, (submission_id,))
            existing = cur.fetchone()

            # Convertir los timestamps enteros a datetime
            dt_timecreated = datetime.fromtimestamp(timecreated)
            dt_timemodified = datetime.fromtimestamp(timemodified)

            if existing:
                # existing[0] es un datetime (timemodified actual)
                if dt_timemodified > existing[0]:
                    # Actualizar
                    cur.execute("""
                        UPDATE documentos_similitud
                        SET course_id = %s,
                            cmid = %s,
                            assign_id = %s,
                            user_id = %s,
                            timecreated = %s,
                            timemodified = %s,
                            filename = %s,
                            fileurl = %s,
                            texto = %s,
                            texto_limpio = %s,
                            fecha_registro = NOW()
                        WHERE moodle_submission_id = %s
                    """, (course_id, cmid, assign_id, user_id,
                          dt_timecreated, dt_timemodified,
                          filename, fileurl, texto, texto_limpio,
                          submission_id))
                    print(f"Documento {submission_id} actualizado.")
                else:
                    print(f"Documento {submission_id} ya está actualizado. No se modifica.")
                    return False
            else:
                # Insertar nuevo
                cur.execute("""
                    INSERT INTO documentos_similitud
                    (course_id, cmid, moodle_submission_id, assign_id, user_id,
                     timecreated, timemodified, filename, fileurl, texto, texto_limpio)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (course_id, cmid, submission_id, assign_id, user_id,
                      dt_timecreated, dt_timemodified,
                      filename, fileurl, texto, texto_limpio))
                print(f"Documento {submission_id} insertado.")
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        print(f"Error en guardar_documento: {e}")
        return False
    finally:
        conn.close()

def obtener_documentos_para_comparar(course_id, cmid, user_id=None):
    """Retorna DataFrame con documentos, usando SQLAlchemy para evitar warnings."""
    engine = create_engine(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')
    try:
        query = """
            SELECT id, moodle_submission_id, assign_id, user_id, filename, fileurl, texto_limpio
            FROM documentos_similitud
            WHERE texto_limpio IS NOT NULL AND texto_limpio <> ''
            AND course_id = %s
            AND cmid = %s
            AND user_id not in (%s)
            ORDER BY id
        """
        df = pd.read_sql(query, engine, params=(course_id, cmid, user_id))
        return df
    finally:
        engine.dispose()

def guardar_resultados_similitud(user_id: int, rows: list):
    """
    Guarda una lista de tuplas en la tabla resultados_similitud.
    Primero elimina todos los registros previos del usuario indicado.
    Cada tupla debe tener el orden:
    (assign_id_similitud, user_id, moodle_submission_id, url, archivo,
     user_id_similitud, moodle_submission_id_similitud, url_similitud,
     archivo_similitud, score_similitud)
    """
    if not rows:
        print("No hay resultados para guardar.")
        return

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Eliminar resultados anteriores del usuario
            cur.execute("DELETE FROM resultados_similitud WHERE user_id = %s", (user_id,))
            print(f"Registros previos eliminados para el usuario {user_id}.")

            # 2. Insertar los nuevos resultados
            execute_values(cur, """
                INSERT INTO resultados_similitud (
                    assign_id_similitud,
                    course_id,
                    cmid,
                    user_id,
                    moodle_submission_id,
                    url,
                    archivo,
                    user_id_similitud,
                    moodle_submission_id_similitud,
                    url_similitud,
                    archivo_similitud,
                    score_similitud
                )
                VALUES %s
            """, rows)
        conn.commit()
        print(f"Resultados guardados correctamente: {len(rows)}")
    finally:
        conn.close()

# ----------------------------------------------------------------------
# Funciones de extracción desde Moodle (actualizadas con PyMuPDF)
# ----------------------------------------------------------------------
def get_submission_status(moodle_url: str, moodle_apikey: str, assign_id: int, user_id: int) -> dict:
    url = f"{moodle_url.rstrip('/')}/webservice/rest/server.php"
    params = {
        "wstoken": moodle_apikey,
        "moodlewsrestformat": "json",
        "wsfunction": "mod_assign_get_submission_status",
        "assignid": assign_id,
        "userid": user_id
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()

def get_assignments_from_course_cmid(moodle_url: str, moodle_apikey: str, course_id: int, cmid: int):
    url = f"{moodle_url}/webservice/rest/server.php"
    params = {
        "wstoken": moodle_apikey,
        "moodlewsrestformat": "json",
        "wsfunction": "mod_assign_get_assignments",
        "courseids[0]": course_id
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    for course in data.get("courses", []):
        for a in course.get("assignments", []):
            if a.get("cmid") == cmid:
                return {
                    "assignmentid": a.get("id"),
                    "cmid": a.get("cmid"),
                    "name": a.get("name")
                }
    return None

def extract_text_pymupdf(pdf_path: str) -> str:
    """Extrae texto de un PDF usando PyMuPDF (fitz) con manejo robusto de codificación."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            # Obtener texto y manejar posibles problemas de codificación
            page_text = page.get_text()
            if page_text:
                # Intentar decodificar/limpiar el texto
                try:
                    # Asegurar que el texto sea válido
                    if isinstance(page_text, bytes):
                        page_text = page_text.decode('utf-8', errors='ignore')
                    elif isinstance(page_text, str):
                        # Eliminar caracteres no imprimibles
                        page_text = ''.join(char for char in page_text if ord(char) >= 32 or char in '\n\r\t')
                except:
                    # Si falla, eliminar caracteres no ASCII
                    page_text = ''.join(char for char in str(page_text) if ord(char) < 128)
                
                text += page_text + "\n"
        doc.close()
    except Exception as e:
        print(f"Error extrayendo texto con PyMuPDF: {e}")
        # Intentar método alternativo si falla
        try:
            with open(pdf_path, 'rb') as f:
                # Leer como binario y decodificar ignorando errores
                raw_data = f.read()
                # Intentar decodificar con latin-1 que acepta cualquier byte
                text = raw_data.decode('latin-1', errors='ignore')
                # Limpiar caracteres de control
                text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        except:
            text = ""
    return text.strip()

def moodle_login(session: requests.Session, moodle_url: str, username: str, password: str) -> None:
    login_url = f"{moodle_url}/login/index.php"
    r = session.get(login_url, timeout=60)
    r.raise_for_status()
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', r.text)
    logintoken = m.group(1) if m else None
    payload = {"username": username, "password": password}
    if logintoken:
        payload["logintoken"] = logintoken
    r2 = session.post(login_url, data=payload, timeout=60, allow_redirects=True)
    r2.raise_for_status()
    if "loginerrors" in r2.text.lower() or "/login/index.php" in r2.url:
        raise RuntimeError("Login falló en Moodle.")

def extraer_metadatos_pdf(data: dict):
    """
    Extrae fileurl, filename, submission_id, timecreated, timemodified
    de la respuesta de get_submission_status.
    Retorna (fileurl, filename, submission_id, timecreated, timemodified) o (None,)*5
    """
    submission = data.get("lastattempt", {}).get("submission", {})
    plugins = submission.get("plugins", [])

    for plugin in plugins:
        if plugin.get("type") != "file":
            continue
        for filearea in plugin.get("fileareas", []):
            for file_info in filearea.get("files", []):
                filename = file_info.get("filename", "")
                mimetype = file_info.get("mimetype", "")
                fileurl = file_info.get("fileurl")
                if filename.lower().endswith(".pdf") or mimetype == "application/pdf":
                    submission_id = submission.get("id")
                    timecreated = submission.get("timecreated")
                    timemodified = submission.get("timemodified")
                    return fileurl, filename, submission_id, timecreated, timemodified
    return None, None, None, None, None

def descargar_pdf_desde_fileurl(session: requests.Session, fileurl: str) -> str:
    if not fileurl:
        raise ValueError("fileurl está vacío o es None.")
    download_url = fileurl.replace("/webservice/", "/")
    response = session.get(download_url, timeout=120, stream=True, allow_redirects=True)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="moodle_") as tmp_file:
        temp_pdf_path = tmp_file.name
    with open(temp_pdf_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)
    # Verificación rápida de cabecera PDF
    with open(temp_pdf_path, "rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        os.remove(temp_pdf_path)
        raise RuntimeError("El archivo descargado no es un PDF válido.")
    return temp_pdf_path

def extraer_texto_desde_fileurl(session: requests.Session, fileurl: str) -> str:
    pdf_path = None
    try:
        pdf_path = descargar_pdf_desde_fileurl(session, fileurl)
        texto = extract_text_pymupdf(pdf_path)
        
        # Si no se pudo extraer texto, intentar con método alternativo
        if not texto:
            print("No se pudo extraer texto con PyMuPDF, intentando método alternativo...")
            try:
                # Intentar con pdftotext si está disponible
                import subprocess
                result = subprocess.run(['pdftotext', '-layout', pdf_path, '-'], 
                                      capture_output=True, text=True, timeout=30)
                texto = result.stdout
            except ImportError:
                print("pdftotext no está disponible")
            except Exception as e:
                print(f"Método alternativo falló: {e}")
                texto = ""
        
        return texto
    except Exception as e:
        print(f"Error en extraer_texto_desde_fileurl: {e}")
        return ""
    finally:
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass

# ----------------------------------------------------------------------
# Endpoint principal
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {"mensaje": "API de similitud activa (versión TF-IDF con PyMuPDF)"}

@app.post("/similitud")
def buscar_similitud(payload: ConsultaSimilitudRequest):
    try:
        # 1. Obtener el assignment a partir del cmid
        assign_data = get_assignments_from_course_cmid(
            MOODLE_URL, MOODLE_APIKEY, payload.course_id, payload.cmid
        )
        if not assign_data:
            raise HTTPException(status_code=404, detail="No se encontró el assignment para el cmid dado.")
        assign_id = assign_data["assignmentid"]

        # 2. Obtener el estado de la entrega del usuario
        data = get_submission_status(MOODLE_URL, MOODLE_APIKEY, assign_id, payload.user_id)

        # 3. Extraer metadatos del PDF
        fileurl, filename, submission_id, timecreated, timemodified = extraer_metadatos_pdf(data)
        if not fileurl:
            raise HTTPException(status_code=404, detail="No se encontró ningún archivo PDF en la entrega.")

        # 4. Descargar y extraer texto del PDF
        with requests.Session() as s:
            s.verify = False
            s.headers.update({"User-Agent": "Mozilla/5.0"})
            moodle_login(s, MOODLE_URL, MOODLE_USERNAME, MOODLE_PASSWORD)
            texto = extraer_texto_desde_fileurl(s, fileurl)

        if not texto:
            raise HTTPException(status_code=404, detail="No se pudo extraer texto del PDF.")

        # 5. Guardar el documento en la base de datos
        guardar_documento(
            course_id=payload.course_id,
            cmid=payload.cmid,
            submission_id=submission_id,
            assign_id=assign_id,
            user_id=payload.user_id,
            timecreated=timecreated,
            timemodified=timemodified,
            filename=filename,
            fileurl=fileurl,
            texto=texto
        )

        # 6. Obtener todos los documentos existentes
        df_existentes = obtener_documentos_para_comparar(payload.course_id,payload.cmid,payload.user_id)
        if df_existentes.empty:
            return {
                "ok": True,
                "mensaje": "No hay documentos previos en la base de datos con los cuales comparar.",
                "resultados": []
            }
        
        

        # 7. Calcular similitud TF-IDF + coseno con los parámetros solicitados
        textos_todos = [limpiar_texto(texto)] + df_existentes["texto_limpio"].tolist()
        vectorizer = TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True
        )
        vectors = vectorizer.fit_transform(textos_todos).toarray()
        cos_sim = cosine_similarity([vectors[0]], vectors[1:]).flatten()

        # 8. Filtrar por umbral de similitud y obtener los top_k
        # Crear lista de tuplas (índice, score) para todos los que superan el umbral
        indices_con_score = [(i, score) for i, score in enumerate(cos_sim) if score >= payload.threshold]
        
        # Ordenar por score descendente
        indices_con_score.sort(key=lambda x: x[1], reverse=True)
        
        # Tomar los top_k
        indices_top = [idx for idx, score in indices_con_score[:payload.top_k]]

        # 9. Preparar filas para insertar en resultados_similitud (solo los que pasan el filtro)
        rows = []
        resultados_ordenados = []  # Para la respuesta
        for idx in indices_top:
            score = cos_sim[idx]
            row_existente = df_existentes.iloc[idx]
            rows.append((
                int(assign_id),
                int(payload.course_id),
                int(payload.cmid),
                int(payload.user_id),
                int(submission_id),
                str(fileurl),
                str(filename),
                int(row_existente["user_id"]),
                int(row_existente["moodle_submission_id"]),
                str(row_existente["fileurl"]),
                str(row_existente["filename"]),
                float(score)
            ))
            resultados_ordenados.append({
                "score": round(score, 4),
                "user_id_similitud": int(row_existente["user_id"]),
                "moodle_submission_id_similitud": int(row_existente["moodle_submission_id"]),
                "archivo_similitud": row_existente["filename"],
                "url_similitud": row_existente["fileurl"],
                "texto_preview": (row_existente["texto_limpio"] or "")[:200]
            })

        # 10. Guardar resultados en la tabla (con limpieza previa)
        try:
            if rows:  # Solo guardar si hay resultados
                guardar_resultados_similitud(payload.user_id, rows)
            else:
                # Si no hay resultados, eliminar los anteriores
                conn = get_db_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM resultados_similitud WHERE user_id = %s", (payload.user_id,))
                    conn.commit()
                    print(f"Registros previos eliminados para el usuario {payload.user_id} (sin nuevos resultados)")
                finally:
                    conn.close()
        except Exception as e:
            print(f"Error guardando resultados: {e}")

        # 11. Retornar respuesta
        return {
            "ok": True,
            "total": len(resultados_ordenados),
            "threshold_aplicado": payload.threshold,
            "top_k_solicitado": payload.top_k,
            "resultados": resultados_ordenados
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))