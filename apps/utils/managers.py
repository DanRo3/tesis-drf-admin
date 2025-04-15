import json
import os
import base64
from apps.utils.enums import RolType
import openai
import requests
from django.conf import settings
from openai import OpenAI
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import status
from apps.chat.models import Chat, Message
from apps.chat.serializers import MessageSerializer
from django.conf import settings
from django.core.files.base import ContentFile
from apps.chat.tools import GenerateImageTool
from .constance import SYSTEM_MESSAGE

API_KEY = settings.API_KEY_OPEN_AI
client = OpenAI(api_key=API_KEY)
 
class Formatted_Messages_Manager:
    """ Class that is responsible for preparing messages to pass them through context. """
    
    def __get_mimetype(self, image_path):
        """Obtiene el mime type basado en la extensión del archivo"""
        extension = os.path.splitext(image_path)[1].lower().replace('.', '')
        if extension == 'jpg':
            extension = 'jpeg'
        return extension
    
    def __convert_path(self, image_path):
        return os.path.normpath(str(image_path))
    
    def __encode_image_to_base64(self, image_path):
        """ Method to encode an image to base64. """
        complete_image_path = f"{settings.BASE_DIR}{image_path}"
        converted_path = self.__convert_path(complete_image_path)
        try:
            with open(converted_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_string
        except FileNotFoundError:
            return Response(
                {"error": "Image not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
         
    def create_formated_message(self, chat:Chat):
        chat_messages = Message.objects.filter(chat_room=chat, is_active=True)
        serialized_messages = MessageSerializer(chat_messages, many=True).data
        formated_messages = [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE,
            }
        ]
        for message in serialized_messages:
            if message.get("rol") == "user":
                if message.get("image"):
                    #Procesar la imagen y convertirla a base64
                    image_base64 = self.__encode_image_to_base64(message.get("image"))
                    mime_type = self.__get_mimetype(message.get("image"))
                    content_parts = [{"type": "text", "text": message["text_message"]}]
                    #Anexar la imagen al contenido
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_type};base64,{image_base64}",
                            },
                        }
                    )
                    formated_messages.append(
                        {
                            "role": message["rol"],
                            "content": content_parts,
                        }
                    )  
                else:
                    formated_messages.append(
                        {
                            "role": message["rol"],
                            "content": message["text_message"],
                        }
                    )
            else:
                formated_messages.append(
                    {
                        "role": message["rol"],
                        "content": message["text_message"]
                    }
                )
        return formated_messages


class GPT_Response_Manager:
    """ Class that is responsible for returning the Openai GPT response. """
    image_service = GenerateImageTool()
    tools_list = [
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "Cuando el usuario solicita crear una imagen, se debe generar una imagen con la descripción proporcionada.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "La descripción de la imagen que se desea generar.",
                        },
                    },
                    "required": ["prompt"]
                },
                "output": {
                    "type": "string",
                    "description": "url de la imagen creada por el prompt del usuario"
                }
            },
        },
    ]

    def __handler_image(self, image_url:str, prompt_openai:str):
        """ Method to handle the image response. """
        try:
            response = requests.get(image_url, timeout=25)
            response.raise_for_status()
            image_content = response.content
            
            file_name = f"imagen: {prompt_openai[:100]}.png"
            imagen = ContentFile(image_content, name=file_name)
            return imagen
        except Exception as e:
            return Response(
                {"error": "Error processing image."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def generate_response(self, formated_messages:list, chat:Chat):
        """ Method to generate a response. """
        try:
            # Realiza la solicitud a la API de OpenAI
            first_response = client.chat.completions.create(
                model="gpt-4o",
                messages=formated_messages,
                tools=self.tools_list,
                tool_choice="auto",
                stream=False,
            )
            # Maneja la respuesta del modelo y las posibles llamadas a funciones
            pre_message = first_response.choices[0].message
            if not pre_message.tool_calls:
                msg = client.chat.completions.create(
                    model="gpt-4o",
                    messages=formated_messages,
                    stream=False,
                )
                model_message = Message(chat_room=chat,rol=RolType.assistant,text_message=msg.choices[0].message.content)
                model_message.save()
                return model_message
            for tool_call in pre_message.tool_calls:
                if tool_call.type == "function":
                    if tool_call.function.name == "generate_image":
                        tool_call_arguments = json.loads(tool_call.function.arguments)
                        image_url, prompt_openai = self.image_service.generate_image(prompt=tool_call_arguments.get("prompt"))
                        formated_messages.append(pre_message)
                        formated_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": image_url,
                        })
                        formated_messages.append({
                            "role": "user",
                            "content": f"Devuelveme en un mensaje solo la siguiente url: {image_url}"
                        })
            msg2 = client.chat.completions.create(
                model="gpt-4o",
                messages=formated_messages,
                stream=False,
            )
            image = self.__handler_image(image_url=msg2.choices[0].message.content, prompt_openai=prompt_openai)
            model_message2 = Message(chat_room=chat,rol=RolType.assistant,text_message=str(prompt_openai),image=image)
            model_message2.save()
            return model_message2
        except openai.AuthenticationError as e:
            raise ValidationError({"error": "Credenciales no válidas para la API de OpenAI."}) from e
        except openai.RateLimitError as e:
            raise ValidationError({"error": "Se ha excedido el límite de solicitudes. Intente más tarde."}) from e
        except openai.APIError as e:
            raise ValidationError({"error": "Ha ocurrido un error en la API de OpenAI. Intente nuevamente."}) from e
        except openai.OpenAIError as e:
            raise ValidationError({"error": "Ha ocurrido un error general al procesar la solicitud en OpenAI."}) from e
        except (AttributeError, IndexError, KeyError) as e:
            raise ValidationError({"error": "La respuesta de la API no tiene el formato esperado. Intente nuevamente."}) from e
        except Exception as e:
            raise ValidationError({"error": "Ha ocurrido un error inesperado. Consulte los registros para más detalles."}) from e
    

class Streaming_Manager:
    def generate_streaming_response(self, response, model_message:Message):
        completed_message = ""
        """ Method to generate a streaming response. """
        try:
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content_data = chunk.choices[0].delta.content
                    completed_message += content_data
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content, 'status':'streaming' })}\n\n"
                    
                if chunk.choices[0].finish_reason == "stop":
                    model_message.text_message = completed_message
                    model_message.save()
                    yield f"data: {json.dumps({'status': 'done'})}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'status': 'error'})}\n\n"