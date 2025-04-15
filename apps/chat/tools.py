# --- En views.py o preferiblemente en un archivo dedicado (e.g., utils/tools.py) ---
import requests
import json
from langchain.tools import tool
from django.conf import settings # Para obtener la URL del MAS

# Obtén la URL base de tu servicio MAS desde la configuración de Django
# Ejemplo en settings.py: MAS_API_URL = "http://localhost:8000" # O la URL real
MAS_API_URL = getattr(settings, "MAS_API_URL", None)
MAS_QUERY_ENDPOINT = "/api/query" # El endpoint específico

@tool
def query_historical_data_system(user_query: str) -> str:
    """
    Use this tool ONLY when the user asks specific questions about historical maritime data,
    requests summaries of historical records, asks for analysis, or requests visualizations
    (like charts or graphs) based on historical maritime data (ships, captains, ports, dates, voyages, etc.).
    Do NOT use this tool for general conversation, greetings, or questions unrelated to maritime history.
    Input should be the user's question exactly as they asked it.
    The tool will return a JSON string with the analysis, text response, potential visualization data, or an error from the specialized system.
    """
    if not MAS_API_URL:
        return json.dumps({"error": "MAS service URL not configured."})

    full_url = MAS_API_URL.rstrip('/') + MAS_QUERY_ENDPOINT
    headers = {"Content-Type": "application/json"}
    payload = {"query": user_query}

    try:
        response = requests.post(full_url, headers=headers, json=payload, timeout=60) # Timeout más largo para MAS
        response.raise_for_status() # Lanza excepción para errores HTTP 4xx/5xx

        # Devuelve el cuerpo de la respuesta JSON como un string
        # El agente recibirá este string y lo incluirá en su razonamiento/respuesta final.
        # La lógica de Django parseará este string luego desde los 'intermediate_steps'.
        return response.text # response.text contiene el JSON string crudo

    except requests.exceptions.Timeout:
        return json.dumps({"error": f"Request to MAS timed out after 60 seconds."})
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": f"Could not connect to the MAS service at {full_url}."})
    except requests.exceptions.HTTPError as e:
        # Intenta obtener más detalles del error si es posible
        error_detail = e.response.text
        return json.dumps({"error": f"MAS service returned an HTTP error {e.response.status_code}. Details: {error_detail}"})
    except Exception as e:
        # Captura cualquier otro error inesperado
        return json.dumps({"error": f"An unexpected error occurred when calling the MAS service: {str(e)}"})