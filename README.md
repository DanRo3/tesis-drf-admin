
# 🤖💬 Tesis Backend: Sistema Multiagente Chat - Gestión y Proxy

**Proyecto de Tesis: Backend Django REST Framework para la gestión de usuarios, chats, historial y proxy al servicio de IA multiagente (MAS).**

---

## 📝 Resumen del Proyecto

Este repositorio contiene el código del backend principal desarrollado con Django REST Framework para el proyecto de tesis de un Sistema Multiagente de IA. Este backend es el punto central para la **gestión de usuarios, la persistencia del historial de conversaciones y la orquestación de llamadas al servicio de IA multiagente (MAS)**, que es otro servicio backend implementado en FastAPI.

Actúa como un proxy entre el frontend (implementado en React) y el servicio MAS. El frontend se comunica únicamente con este backend Django para todas las operaciones (autenticación, gestión de chats, envío de mensajes y recepción de respuestas procesadas por la IA), y este backend, a su vez, se comunica con el servicio MAS cuando una consulta requiere procesamiento por parte de la inteligencia artificial.

## ✨ Características Principales

*   **Autenticación de Usuarios:** Gestión segura de usuarios utilizando Django y DRF con tokens JWT (vía Djoser y Simple JWT).
*   **Gestión de Chats:** Creación, listado y recuperación de sesiones de chat para cada usuario.
*   **Historial de Conversaciones:** Almacenamiento persistente de mensajes de usuario y respuestas del asistente IA en la base de datos.
*   **Proxy al Servicio MAS:** Un endpoint dedicado para recibir consultas del frontend, llamar al servicio MAS (FastAPI) vía HTTP, y procesar su respuesta.
*   **Manejo de Imágenes Generadas por MAS:** Decodifica imágenes en Base64 recibidas del MAS, las guarda como archivos en el servidor Django (`MEDIA_ROOT`), y almacena su ruta relativa en la base de datos.
*   **Serialización de URLs de Imagen:** Devuelve la URL completa de las imágenes guardadas en las respuestas de la API para su visualización en el frontend.
*   **Validación:** Incluye validadores para asegurar la integridad y permisos de los chats.
*   **Paginación:** Implementa paginación para listados de chats y mensajes.

## 🏗️ Arquitectura del Sistema

Este backend forma la capa intermedia en una arquitectura de microservicios (conceptual) de 3 tiers:

1.  **Frontend (React):** Interfaz de usuario. Se comunica **SOLO** con el Backend Django.
2.  **Backend (Django DRF - ESTE PROYECTO):**
    *   Maneja Autenticación, Usuarios, Chats, Mensajes (Base de Datos).
    *   Actúa como **Proxy** para el servicio MAS.
3.  **Servicio MAS (FastAPI):** El motor de IA que procesa consultas de lenguaje natural y genera respuestas/visualizaciones. Es llamado **SOLO** por el Backend Django.

```
+-----------------+      (API: Auth, Chat, Msgs, Query)      +-------------------------+      (HTTP POST /api/query)      +-------------------------+
|  Frontend React | <--------------------------------------> | Backend Django (DRF)    | ---------------------------> | Servicio MAS (FastAPI)  |
| (User Browser)  |                                          | (Users, Chats, Msgs DB, |                               | (AI Processing, FAISS, |
+-----------------+                                          |  Proxy to MAS)          | <--------------------------- |  LLM, Image Gen)        |
                                                              +-------------------------+  (JSON Response w/ img_path)  +-------------------------+
```

## 🛠️ Tecnologías Utilizadas

*   **Backend Framework:** Django
*   **REST Framework:** Django REST Framework (DRF)
*   **Autenticación:** Djoser, Django REST Framework Simple JWT
*   **ORM:** Django ORM (PostgreSQL, SQLite, etc.)
*   **Interacción con MAS:** `requests`, `httpx` (para llamadas HTTP)
*   **Integración IA/Agentes:** `langchain`, `langchain-openai` (para el agente que decide usar la herramienta MAS), `python-dotenv`
*   **Manejo de Archivos:** Django's `ImageField`, `ContentFile`, `default_storage`, `base64`, `uuid`, `re`
*   **Utilidades:** `django-cors-headers`, `django-environ`, `psycopg2` (o conector DB)
*   **Base de Datos:** PostgreSQL (configuración por defecto en `DATABASE_URL`), u otra soportada por Django.

## 📂 Estructura del Proyecto

```
/tesis-drf-admin/
├── core/                       # Configuración principal del proyecto Django
│   ├── settings.py             # Configuración general (DB, Apps, URLs, Auth, Media, MAS_API_URL)
│   ├── urls.py                 # URLs principales (admin, api, auth)
│   └── ...
├── apps/                       # Aplicaciones Django del proyecto
│   ├── chat/                   # Lógica principal de chats y mensajes
│   │   ├── models.py           # Modelos Chat y Message (con Image CharField)
│   │   ├── serializers.py      # Serializers (con MessageSerializer.image_url)
│   │   ├── views.py            # API Views (ChatViewSet, MessageCreateAV - proxy)
│   │   ├── urls.py             # URLs de la app chat
│   │   ├── langchain_setup.py  # Configuración del agente LangChain y herramientas
│   │   ├── tools.py            # Herramienta query_historical_data_system (llama a MAS, guarda imagen)
│   │   ├── validators.py       # Validadores personalizados
│   │   └── ...
│   ├── utils/                  # Utilidades generales (modelos base, enums, paginación)
│   │   ├── models.py           # BaseModel, etc.
│   │   ├── serializers.py      # AbstractBaseSerializer
│   │   └── ...
│   └── ...
├── media/                      # Directorio para archivos subidos/generados (configurado por MEDIA_ROOT)
│   └── mas_images/             # Subcarpeta para imágenes del MAS (configurado por MAS_IMAGE_UPLOAD_SUBDIR/upload_to)
├── .env.example                # Archivo de ejemplo para variables de entorno
├── manage.py                   # Utilidad de línea de comandos de Django
├── requirements.txt            # Dependencias del proyecto
└── README.md                   # Este archivo
```

## 🚀 Cómo Empezar

### Prerrequisitos

*   Python 3.9+
*   pip (gestor de paquetes de Python)
*   Un sistema de base de datos (PostgreSQL recomendado, o usar SQLite para empezar)
*   Git
*   **Servicio MAS (FastAPI) corriendo y accesible** (su URL debe ser configurada).

### 1. Clonar el Repositorio

```bash
git clone <url-del-repositorio>
cd tesis-drf-admin
```

### 2. Crear Entorno Virtual (Recomendado)

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno

Copia el archivo de ejemplo y edítalo con tus configuraciones:

```bash
cp .env.example .env
```

Abre el archivo `.env` y define las variables necesarias:

```dotenv
# .env

# Clave secreta para la instalación de Django
SECRET_KEY='pon_una_clave_secreta_unica_aqui_para_produccion'

# Configuración de base de datos (ejemplo para PostgreSQL)
# DATABASE_URL='postgres://user:password@host:port/database_name'
# Ejemplo para SQLite (para desarrollo rápido)
DATABASE_URL='sqlite:///db.sqlite3'

# Clave API para OpenAI (usada por el agente LangChain)
API_KEY_OPEN_AI='tu_clave_api_openai'

# URL base de tu servicio MAS (FastAPI)
MAS_API_URL='http://127.0.0.1:8008' # AJUSTA si tu MAS corre en otro host o puerto

# Nombre de la subcarpeta dentro de MEDIA_ROOT para imágenes del MAS (debe coincidir con models.py upload_to)
MAS_IMAGE_UPLOAD_SUBDIR='mas_images' # Debe coincidir con Message.image upload_to (si es charfield, solo el nombre de la subcarpeta)
```

### 5. Configurar Base de Datos

Aplica las migraciones para crear las tablas de la base de datos:

```bash
python manage.py migrate
```

Crea un superusuario para acceder al panel de administración de Django:

```bash
python manage.py createsuperuser
```

### 6. Crear Directorios Media

Crea manualmente los directorios donde se guardarán los archivos media:

```bash
mkdir media
mkdir media/mas_images # O el nombre que definiste en MAS_IMAGE_UPLOAD_SUBDIR y upload_to
```

Asegúrate de que el usuario bajo el cual se ejecuta el servidor de Django tenga **permisos de escritura** en estos directorios.

### 7. Ejecutar el Servidor de Desarrollo

Asegúrate de que tu **servicio MAS (FastAPI) esté corriendo** y accesible en la `MAS_API_URL` configurada.

Luego, inicia el servidor de desarrollo de Django:

```bash
python manage.py runserver 0.0.0.0:8000 # O el puerto que prefieras (ej. 8008 para evitar conflicto con MAS)
```

*   `0.0.0.0:8000`: Hace que el servidor sea accesible externamente (útil si el frontend corre en otro dispositivo o contenedor). Ajusta el puerto si es necesario.

La API estará disponible en `http://localhost:8000/api/` (o el puerto que uses).

## 🔑 Autenticación

Este backend utiliza autenticación basada en tokens JWT.

*   Para obtener un token de acceso y refresco, envía una petición `POST` a `/auth/jwt/create/` con el `username` y `password` de un usuario existente.
*   Incluye el token de acceso (`access`) en el header `Authorization: JWT <your_access_token>` para acceder a los endpoints protegidos (`IsAuthenticated`).
*   Utiliza `/auth/jwt/refresh/` para obtener un nuevo token de acceso usando un token de refresco válido.
*   Utiliza `/auth/users/` (y sus sub-rutas) para la gestión de usuarios (registro, etc., según la configuración de Djoser).

## 📚 API Endpoints

Los endpoints principales están bajo el prefijo `/api/chat/` (si configuraste la app `chat` bajo `/api/` en `core/urls.py`).

*   `POST /api/chats/` - Crear un nuevo chat.
*   `GET /api/chats/` - Listar chats del usuario autenticado.
*   `GET /api/chats/{uuid}/` - Recuperar detalles de un chat específico (incluye mensajes).
*   `DELETE /api/chats/{uuid}/` - Eliminar (soft delete) un chat.
*   `POST /api/chats/{uuid}/messages/` - **Endpoint principal de interacción.** Envía un mensaje de usuario, llama al servicio MAS (proxy), procesa su respuesta (incluyendo guardar imagen si aplica), guarda el mensaje del asistente y lo retorna.
    *   Request Body: `{"text_message": "Tu consulta aquí"}`
    *   Response Body: Devuelve el objeto `Message` guardado del asistente (incluye `image_url` si hubo imagen).
*   `POST /api/chats/{uuid}/messages/interaction/` - Registrar interacciones (like/dislike) con un mensaje.

Puedes explorar la documentación interactiva (Swagger UI / ReDoc) si la tienes configurada con DRF.

## 🖼️ Manejo de Archivos Media

Los archivos generados por el servicio MAS (imágenes de gráficos) se guardan en el servidor Django.

*   Se almacenan en el directorio configurado por `MEDIA_ROOT` (ej. `./media/`) dentro de la subcarpeta `MAS_IMAGE_UPLOAD_SUBDIR` (ej. `./media/mas_images/`).
*   En desarrollo (`DEBUG=True`), Django sirve automáticamente estos archivos bajo la URL configurada en `MEDIA_URL` (ej. `/media/`). La URL completa sería `http://localhost:8000/media/mas_images/nombre_del_archivo.png`.
*   El frontend React debe usar la `image_url` proporcionada en la respuesta JSON (que construirá la URL completa) para mostrar la imagen.

**Para producción:** Deberás configurar un servidor web (Nginx, Apache) o un servicio de almacenamiento en la nube (AWS S3, DigitalOcean Spaces) para servir los archivos en `MEDIA_ROOT` bajo la `MEDIA_URL`. La configuración `static(settings.MEDIA_URL, ...)` en `urls.py` es SÓLO para desarrollo.

---

*Este proyecto es parte de una tesis. Las contribuciones externas podrían ser consideradas pero deben alinearse con los objetivos académicos.*


