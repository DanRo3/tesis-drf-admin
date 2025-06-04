# apps/chat/tools.py
import requests
import json
import logging
import base64
import uuid
import re
import os # Asegúrate de importar os
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage # Importar default_storage
from django.conf import settings
from langchain.tools import tool

logger = logging.getLogger(__name__)

MAS_API_URL = getattr(settings, "MAS_API_URL", None)
MAS_QUERY_ENDPOINT = "/api/query"
MAS_IMAGE_UPLOAD_SUBDIR = getattr(settings, "MAS_IMAGE_UPLOAD_SUBDIR", "chat_images")


@tool
def query_historical_data_system(user_query: str) -> str:
    """
    Use this tool ONLY for questions that REQUIRE accessing or analyzing specific historical maritime data (ships, captains, ports, dates, voyages) or generating visualizations from this data.
    DO NOT use this tool for general questions, greetings, or any topic NOT directly related to maritime historical records.
    Input should be the user's exact query.
    """
    logger.info(f"Tool 'query_historical_data_system' invoked with query: '{user_query}'")
    if not MAS_API_URL:
        logger.error("MAS_API_URL no está configurado en settings.py.")
        return json.dumps({"error": "Configuración incorrecta: El servicio de datos históricos no está disponible.", "text_response": None, "image_path": None})

    full_url = MAS_API_URL.rstrip('/') + MAS_QUERY_ENDPOINT
    headers = {"Content-Type": "application/json"}
    payload = {"query": user_query}

    # --- Inicializar la respuesta final que se devolverá ---
    final_mas_response = {
        "text_response": None,
        "image_path": None, # Aquí se almacenará la ruta relativa si se guarda una imagen
        "error": None
    }

    try:
        logger.debug(f"Enviando POST a MAS: {full_url} con payload: {payload}")
        response = requests.post(full_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        try:
            mas_data = response.json()
            logger.debug(f"Respuesta JSON cruda del MAS: {mas_data}")

            # Asignar text_response y error del MAS si existen en el JSON
            final_mas_response["text_response"] = mas_data.get("text_response")
            final_mas_response["error"] = mas_data.get("error") # Error lógico del MAS

            mas_base64_image = mas_data.get("image_response")

            # --- Procesar y guardar la imagen si se recibió Base64 ---
            if mas_base64_image:
                logger.info("Base64 de imagen recibido del MAS. Intentando guardar como archivo...")
                try:
                    if isinstance(mas_base64_image, str) and ";base64," in mas_base64_image:
                        header, encoded_data = mas_base64_image.split(",", 1)
                        image_data_bytes = base64.b64decode(encoded_data)

                        extension = "png" # Default
                        mime_type_match = re.search(r"data:image/(\w+);base64", header)
                        if mime_type_match:
                            ext = mime_type_match.group(1).lower()
                            if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']: extension = ext
                            else: extension = "png" # Default si no es segura

                        filename_only = f"mas_viz_{uuid.uuid4()}.{extension}"
                        relative_upload_path = os.path.join(MAS_IMAGE_UPLOAD_SUBDIR, filename_only)

                        logger.info(f"Guardando archivo en: {relative_upload_path} (relativo a MEDIA_ROOT)")
                        # --- ¡AQUÍ ES DONDE SE GUARDA Y SE OBTIENE LA RUTA CORRECTA! ---
                        saved_file_path = default_storage.save(relative_upload_path, ContentFile(image_data_bytes))
                        # default_storage.save devuelve la ruta relativa real donde se guardó


                        # --- ¡ASIGNAR LA RUTA GUARDADA A LA RESPUESTA FINAL! ---
                        final_mas_response["image_path"] = saved_file_path # <--- ¡CORREGIDO AQUÍ!

                        # Ajustar text_response si solo era un mensaje genérico de "gráfico generado" del MAS
                        if not final_mas_response["text_response"] or "visualizaci" in final_mas_response["text_response"].lower():
                             final_mas_response["text_response"] = "Se generó una visualización para tu consulta." # Mensaje estándar

                    else:
                        logger.warning("Formato Base64 inesperado del MAS.")
                        final_mas_response["error"] = (final_mas_response["error"] or "") + " Error procesando formato de imagen."
                except Exception as img_e:
                    logger.exception(f"Error al guardar la imagen Base64 del MAS: {img_e}")
                    final_mas_response["error"] = (final_mas_response["error"] or "") + f" Error al procesar imagen: {str(img_e)}"

            # Si hubo un error del MAS, pero también texto, el texto podría explicar el error
            # Esto lo dejamos como estaba, solo asegurando que use los campos de final_mas_response
            if final_mas_response["error"] and final_mas_response["text_response"] and final_mas_response["error"] in final_mas_response["text_response"]:
                pass # El error ya está en el texto
            elif final_mas_response["error"] and not final_mas_response["text_response"]:
                final_mas_response["text_response"] = f"Error del sistema de datos: {final_mas_response['error']}"


        except json.JSONDecodeError:
            logger.error(f"Fallo al decodificar JSON de MAS. Contenido: {response.text[:500]}...", exc_info=True)
            final_mas_response["error"] = "El servicio de datos devolvió un formato inválido."
            final_mas_response["text_response"] = "Información no disponible (formato inesperado)."

        # --- Devolver la respuesta final (que ahora incluye image_path si se guardó) ---
        logger.debug(f"Herramienta finalizando, devolviendo JSON: {json.dumps(final_mas_response)}")
        return json.dumps(final_mas_response)

    # ... (resto de los except para requests.exceptions y Exception) ...
    except requests.exceptions.Timeout:
        logger.error(f"Timeout (60s) al llamar al MAS en {full_url}", exc_info=True)
        final_mas_response["error"] = "Servicio de datos tardó demasiado."
        final_mas_response["text_response"] = "Información no disponible (timeout)."
        return json.dumps(final_mas_response)
    except requests.exceptions.ConnectionError:
        logger.error(f"Error de conexión al llamar al MAS en {full_url}", exc_info=True)
        final_mas_response["error"] = "No se pudo conectar al servicio de datos."
        final_mas_response["text_response"] = "Información no disponible (error de conexión)."
        return json.dumps(final_mas_response)
    except requests.exceptions.HTTPError as e:
        logger.error(f"Error HTTP {e.response.status_code} del MAS. Respuesta: {e.response.text[:500]}...", exc_info=True)
        error_detail = e.response.text[:200] # Limitar longitud
        final_mas_response["error"] = f"Servicio de datos devolvió error HTTP {e.response.status_code}."
        final_mas_response["text_response"] = f"Información no disponible (error {e.response.status_code}): {error_detail}"
        return json.dumps(final_mas_response)
    except Exception as e:
        logger.exception(f"Error inesperado llamando al MAS: {e}", exc_info=True)
        final_mas_response["error"] = f"Error inesperado contactando servicio de datos: {str(e)[:100]}"
        final_mas_response["text_response"] = "Información no disponible (error inesperado)."
        return json.dumps(final_mas_response)