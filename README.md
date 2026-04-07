# Similitud API

API REST para detectar similitud en entregas de Moodle usando TF-IDF + cosine similarity.

- Lenguaje: Python 3.11+
- Framework: FastAPI
- DB: PostgreSQL
- Texto PDF: PyMuPDF

## 💡 Objetivo

1. Toma un `course_id`, `cmid` y `user_id`.
2. Consulta Moodle para obtener la entrega del estudiante (PDF).
3. Extrae texto del PDF y limpia contenido.
4. Guarda documento en la tabla `documentos_similitud`.
5. Calcula similitud con documentos existentes (mismo curso + cmid, distinto usuario).
6. Devuelve coincidencias que superen un threshold y guarda en `resultados_similitud`.

## 📦 Estructura de archivos

- `main.py` - lógica principal y endpoints.
- `requirements.txt` - dependencias del proyecto.
- `tables.sql` - scripts de creación de tablas (documentos_similitud, resultados_similitud, etc.).

## 🔧 Configuración de entorno

1. Crear entorno virtual (recomendado):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

2. Instalar dependencias:

```powershell
pip install -r requirements.txt
```


# Configuración Moodle
``` MOODLE_URL = ""
MOODLE_APIKEY = ""
MOODLE_USERNAME = ""
MOODLE_PASSWORD = ""
```

3. Variables de entorno opcionales (si no se usan valores hardcodeados en `main.py`):
- `DB_HOST` (default `localhost`)
- `DB_PORT` (default `5432`)
- `DB_NAME` (default `proyectos_ia`)
- `DB_USER` (default `postgres`)
- `DB_PASSWORD` (default `admin`)

> Nota: En `main.py` hay valores de Moodle (`MOODLE_URL`, `MOODLE_APIKEY`, `MOODLE_USERNAME`, `MOODLE_PASSWORD`) embebidos; ajústalos antes de producción.

4. Crear la base de datos y tablas con `tables.sql`:

```powershell
psql -h <host> -U <user> -d <database> -f tables.sql
```

## 🚀 Ejecutar API

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Acceder a documentación automática:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## 🧪 Endpoints

### GET `/`
- Respuesta: `{ "mensaje": "API de similitud activa (versión TF-IDF con PyMuPDF)" }`

### POST `/similitud`

Cuerpo JSON (`ConsultaSimilitudRequest`):

```json
{
  "course_id": 123,
  "cmid": 45,
  "user_id": 678,
  "top_k": 5,
  "threshold": 0.75
}
```

Respuesta exitosa:

```json
{
  "ok": true,
  "total": 2,
  "threshold_aplicado": 0.75,
  "top_k_solicitado": 5,
  "resultados": [ ... ]
}
```

## 🛠️ Recomendaciones

- Cambiar las credenciales de Moodle y DB a variables de entorno o archivo de configuración seguro.
- Evitar guardar datos de producción en código.
- Controlar excepciones de conexiones a Moodle y PostgreSQL.
- Evaluar la seguridad de `requests` con `verify=False` (actualmente usado en login Moodle).

## 📌 Notas de mantenimiento

- Añadir autenticación (JWT, API Key) al endpoint para protegerlo.
- Implementar paginación y cache para resultados en grandes volúmenes.
- Agregar pruebas unitarias (pytest) cubriendo:
  - `limpiar_texto`.
  - `get_assignment_from_course_cmid`.
  - `extraer_texto_desde_fileurl` (mocked).
  - endpoint `/similitud` con dependencia de DB simulada.

---

> Hecho con ❤️ para `Similitud_api`.
