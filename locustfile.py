# locustfile.py
from locust import HttpUser, task, between, events
import random
import time
import os
from dotenv import load_dotenv # Para cargar variables de entorno si usas .env

load_dotenv() # Carga variables de .env si existe

# --- Configuración de Autenticación (AJUSTA ESTO) ---
# ...
TEST_USERS = [
    {"username": "DanielR", "password": "DanRoNK1911*"},
]

# Endpoint para obtener el token.
# Si tu endpoint de Simple JWT está configurado en la raíz de 'auth/', por ejemplo.
TOKEN_ENDPOINT = "/auth/jwt/create/" # <--- CORREGIDO: SIN /api/

class AuthenticatedUser(HttpUser):
    wait_time = between(1, 5)
    abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.user_credentials = None

    def on_start(self):
        if not TEST_USERS:
            print("ERROR: No TEST_USERS defined for authentication.")
            self.environment.runner.quit()
            return

        user_index = self.environment.runner.worker_index if self.environment.runner else 0
        self.user_credentials = TEST_USERS[user_index % len(TEST_USERS)]

        print(f"Usuario Locust {self.user_credentials['username']} iniciando sesión en {TOKEN_ENDPOINT}...")
        try:
            # Para djangorestframework-simplejwt, los datos se envían como form-data, no JSON.
            # Si tu endpoint espera JSON, usa json=self.user_credentials
            response = self.client.post(TOKEN_ENDPOINT, data=self.user_credentials)
            response.raise_for_status()
            
            json_response = response.json()
            self.token = json_response.get("access") 
            
            if not self.token:
                print(f"ERROR: No se pudo obtener token 'access' para {self.user_credentials['username']}. Respuesta JSON: {json_response}")
                self.environment.runner.quit()
                return
            
            # Para JWT (como los de djangorestframework-simplejwt), el prefijo estándar es "Bearer"
            self.client.headers["Authorization"] = f"JWT {self.token}" # <--- CORREGIDO: Usar "Bearer"
            print(f"Usuario {self.user_credentials['username']} autenticado. Token: ...{self.token[-10:]}") # Imprime solo parte del token

        except Exception as e:
            print(f"ERROR al autenticar a {self.user_credentials['username']}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Respuesta del servidor: Status {e.response.status_code}, Body: {e.response.text}")
            events.request.fire(
                request_type="AUTH",
                name="login_failure",
                response_time=0,
                response_length=0,
                exception=e,
                context=self.user_credentials,
            )
            self.environment.runner.quit()

# --- El resto de tu clase ChatUser y otras definiciones permanecen igual ---
class ChatUser(AuthenticatedUser):
    abstract = False 

    def on_start(self):
        super().on_start() 
        self.created_chat_uids = []
        self.existing_message_uids = {} 

    @task(5) 
    def list_my_chats(self):
        # Las solicitudes ahora usarán el header de autorización configurado en AuthenticatedUser.on_start
        self.client.get("/api/chats/")

    # ... (resto de tus tareas como estaban antes, deberían funcionar ahora que la autenticación está configurada)
    @task(2)
    def create_chat(self):
        payload = {
            "title": f"Chat de Locust {random.randint(1000, 9999)}",
            "description": f"Creado por {self.user_credentials['username']} a las {time.time()}"
        }
        with self.client.post("/api/chats/", json=payload, catch_response=True) as response:
            if response.status_code == 201:
                chat_data = response.json()
                chat_uid = chat_data.get("uid")
                if chat_uid:
                    self.created_chat_uids.append(chat_uid)
                    response.success()
                else:
                    response.failure("Chat creado pero UID no encontrado en la respuesta")
            else:
                response.failure(f"Fallo al crear chat: {response.status_code} - {response.text}")

    @task(10) # Enviar mensajes es la acción principal
    def send_message_to_chat(self):
        if not self.created_chat_uids:
            self.create_chat() 
            if not self.created_chat_uids:
                list_response = self.client.get("/api/chats/")
                if list_response.status_code == 200:
                    chats_data = list_response.json().get("chats", [])
                    self.created_chat_uids.extend([chat['uid'] for chat in chats_data if 'uid' in chat])
                    self.created_chat_uids = list(set(self.created_chat_uids)) 
                if not self.created_chat_uids:
                    # print(f"Usuario {self.user_credentials['username']} no tiene chats para enviar mensajes.") # Comentado para no llenar la consola
                    return 

        target_chat_uid = random.choice(self.created_chat_uids)
        
        message_payload = {
            "text_message": f"Mensaje de prueba de Locust {random.randint(1, 100)} por {self.user_credentials['username']}"
        }
        
        endpoint_url = f"/api/chats/{target_chat_uid}/messages/"
        with self.client.post(endpoint_url, json=message_payload, name="/api/chats/[uid]/messages/ (POST)", catch_response=True) as response:
            if response.status_code == 201:
                message_data = response.json().get("message", {}) 
                message_uid = message_data.get("uid")
                if message_uid:
                    if target_chat_uid not in self.existing_message_uids:
                        self.existing_message_uids[target_chat_uid] = []
                    self.existing_message_uids[target_chat_uid].append(message_uid)
                    response.success()
                else:
                    response.failure("Mensaje enviado pero UID no encontrado en la respuesta del mensaje")
            elif response.status_code == 503:
                response.failure(f"Servicio IA no disponible (503) para chat {target_chat_uid}")
            else:
                response.failure(f"Fallo al enviar mensaje a chat {target_chat_uid}: {response.status_code} - {response.text}")

    @task(3)
    def get_chat_history(self):
        if not self.created_chat_uids:
            return

        target_chat_uid = random.choice(self.created_chat_uids)
        endpoint_url = f"/api/chats/{target_chat_uid}/messages/"
        self.client.get(endpoint_url, name="/api/chats/[uid]/messages/ (GET)")

    @task(1)
    def get_specific_chat_detail(self):
        if not self.created_chat_uids:
            return
        target_chat_uid = random.choice(self.created_chat_uids)
        self.client.get(f"/api/chats/{target_chat_uid}/", name="/api/chats/[uid]/ (GET)")

    @task(1) 
    def delete_chat(self):
        if not self.created_chat_uids:
            return
        
        chat_to_delete_uid = random.choice(self.created_chat_uids)
        
        with self.client.delete(f"/api/chats/{chat_to_delete_uid}/", name="/api/chats/[uid]/ (DELETE)", catch_response=True) as response:
            if response.status_code == 204:
                response.success()
                self.created_chat_uids.remove(chat_to_delete_uid)
                if chat_to_delete_uid in self.existing_message_uids:
                    del self.existing_message_uids[chat_to_delete_uid]
            elif response.status_code == 404: 
                response.success() 
                if chat_to_delete_uid in self.created_chat_uids:
                     self.created_chat_uids.remove(chat_to_delete_uid)
                if chat_to_delete_uid in self.existing_message_uids:
                    del self.existing_message_uids[chat_to_delete_uid]
            else:
                response.failure(f"Fallo al borrar chat {chat_to_delete_uid}: {response.status_code}")

    def on_stop(self):
        print(f"Usuario {self.user_credentials['username']} finalizando.")