#apps/chat/views.py
from typing import Any, Dict, Optional
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.conf import settings
# from django.core.files.base import ContentFile # No parece usarse
from django.http import Http404 # <--- AÑADIDO
from apps.chat.validators import ChatValidators
from apps.utils.paginations import MediumSetPagination
from apps.utils.enums import RolType
from .models import Chat, Message
# from rest_framework import serializers # No es necesario si no se usa directamente aquí
from .serializers import ChatSerializer, ChatDetailSerializer, MessageSerializer
# import base64 # No parece usarse
import json
import traceback
import logging
# import re # No parece usarse
# import uuid # No parece usarse

logger = logging.getLogger(__name__)

# --- LangChain Integration Imports ---
try:
    from apps.chat.langchain_setup import (
        agent_executor,
        load_langchain_history_from_db
    )
    LANGCHAIN_SETUP_SUCCESSFUL = True
    # No imprimas aquí, deja que el logger lo maneje si es necesario o que Django lo haga en modo DEBUG
    # print("INFO: LangChain setup loaded successfully.")
    logger.info("LangChain setup loaded successfully.")
except ImportError as e:
    logger.error(f"Failed to import LangChain setup: {e}. AI assistant features will be disabled.")
    def agent_executor(*args, **kwargs):
        raise NotImplementedError("LangChain agent_executor is not available due to import failure.")
    def load_langchain_history_from_db(*args, **kwargs):
        raise NotImplementedError("LangChain history loader is not available due to import failure.")
    LANGCHAIN_SETUP_SUCCESSFUL = False
except Exception as e:
    logger.error(f"An unexpected error occurred during LangChain setup import: {e}", exc_info=True)
    def agent_executor(*args, **kwargs): raise NotImplementedError("LangChain agent_executor unavailable.")
    def load_langchain_history_from_db(*args, **kwargs): raise NotImplementedError("LangChain history loader unavailable.")
    LANGCHAIN_SETUP_SUCCESSFUL = False

def handle_exceptions(func):
    """
    Decorator to handle common exceptions in ChatViewSet views.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Chat.DoesNotExist:
            logger.warning("Chat.DoesNotExist caught in handle_exceptions decorator.")
            return Response(
                {"error": "Chat data not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Http404 as e: # Para get_object_or_404
            logger.warning(f"Http404 caught in handle_exceptions decorator: {e}")
            return Response(
                {"error": "Resource not found."}, # Puedes usar e.args[0] si quieres el mensaje original
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionDenied as e: # Específico de DRF
            logger.warning(f"PermissionDenied caught in handle_exceptions decorator: {e.detail if hasattr(e, 'detail') else e}")
            return Response(
                {"error": e.detail if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as e: # Específico de DRF
            logger.warning(f"ValidationError caught in handle_exceptions decorator: {e.detail if hasattr(e, 'detail') else e}")
            return Response(
                {"error": e.detail if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e: # Genérico de Python
            logger.warning(f"ValueError caught in handle_exceptions decorator: {e}", exc_info=True)
            return Response(
                {"error": f"Invalid value: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unhandled exception in decorated view ({func.__name__}): {e.__class__.__name__} - {e}", exc_info=True)
            return Response(
                {"error": "An unexpected server error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    return wrapper


class ChatViewSet(viewsets.ModelViewSet):
    queryset = Chat.objects.filter(is_active=True)
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]

    @handle_exceptions # El decorador ahora maneja Http404, PermissionDenied, ValidationError
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().filter(registered_by=request.user).order_by('-created_at')
        paginator = MediumSetPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_queryset, many=True)
        return paginator.get_paginated_response({"chats": serializer.data})

    # create no necesita el decorador si se confía en DRF para manejar ValidationError del serializer
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True) # DRF convierte esto a 400
        serializer.save(registered_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @handle_exceptions # El decorador ahora maneja Http404, PermissionDenied
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object() # Puede lanzar Http404 si no se encuentra (DRF lo hace)
        if instance.registered_by != request.user:
            # Esto debería ser manejado por DRF o por un validador,
            # pero una comprobación explícita es segura.
            # El decorador lo capturará si lanzas PermissionDenied aquí.
            raise PermissionDenied("You do not have permission to access this chat.")
        serializer = ChatDetailSerializer(instance)
        return Response({"chat": serializer.data}, status=status.HTTP_200_OK)

    @handle_exceptions # El decorador ahora maneja Http404, PermissionDenied
    def destroy(self, request, *args, **kwargs):
        instance_chat = self.get_object() # Puede lanzar Http404
        if instance_chat.registered_by != request.user:
            raise PermissionDenied("You do not have permission to delete this chat.")

        if not instance_chat.is_active:
            # Esto es una lógica de negocio, no una excepción estándar de DRF.
            # La respuesta 400 aquí es apropiada.
            return Response(
                {"detail": "This chat is already inactive."}, # Usar 'detail' es común en DRF para mensajes
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance_chat.soft_delete()
        return Response(
            # "message" está bien, pero "detail" es más común para mensajes no erróneos sin cuerpo
            {"detail": "Chat deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class MessageCreateAV(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    chat_validator = ChatValidators()

    def get(self, request, *args, **kwargs):
        chat_uid = kwargs.get('pk')
        if not chat_uid:
             return Response({"error": "Chat UID not provided in URL."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # get_object_or_404 lanza Http404, que DRF convierte a una respuesta 404.
            chat = get_object_or_404(Chat, uid=chat_uid)
            self.chat_validator.validate(chat=chat, request=request) # Puede lanzar PermissionDenied

            queryset = Message.objects.filter(chat_room=chat, is_active=True).order_by('created_at')
            serializer = self.serializer_class(queryset, many=True)
            return Response({"history": serializer.data}, status=status.HTTP_200_OK)

        # DRF convierte PermissionDenied a una respuesta 403.
        # DRF convierte Http404 a una respuesta 404.
        # No es estrictamente necesario capturarlos aquí a menos que quieras personalizar el cuerpo de la respuesta.
        except Http404:
            logger.warning(f"Chat not found in MessageCreateAV.get for UID: {chat_uid}")
            return Response({"error": "Chat not found."}, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied as e:
            logger.warning(f"Permission denied in MessageCreateAV.get: {e.detail if hasattr(e, 'detail') else e}")
            return Response({"error": e.detail if hasattr(e, 'detail') else str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Unexpected error in GET MessageCreateAV: {e.__class__.__name__} - {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred retrieving history."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        if not LANGCHAIN_SETUP_SUCCESSFUL:
             logger.error("LangChain setup unsuccessful, MessageCreateAV.post returning 503.")
             return Response(
                 {"error": "El asistente IA no está disponible actualmente debido a un problema de configuración."},
                 status=status.HTTP_503_SERVICE_UNAVAILABLE
             )

        chat_uid = kwargs.get('pk')
        if not chat_uid:
             logger.warning("Chat UID not provided in URL for MessageCreateAV.post.")
             return Response({"error": "Chat UID no proporcionado en la URL."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # get_object_or_404 con filtro asegura que el chat pertenece al usuario y está activo.
            # Esto lanzará Http404 si no se cumple, DRF lo convierte a 404.
            chat = get_object_or_404(Chat.objects.filter(registered_by=request.user, is_active=True), uid=chat_uid)
            # El validador podría ser redundante si el get_object_or_404 ya verifica la pertenencia.
            # self.chat_validator.validate(request, chat) # Si este validador hace más cosas, mantenlo.
            logger.debug(f"Chat {chat.uid} validation successful for post.")

            chat_has_title = bool(chat.title)
            serializer = self.serializer_class(data=request.data, context={'request': request})
            # is_valid(raise_exception=True) lanza ValidationError, DRF lo convierte a 400.
            serializer.is_valid(raise_exception=True)
            user_message_instance = serializer.save(chat_room=chat, rol=RolType.user)
            user_input_text = user_message_instance.text_message
            logger.info(f"User message saved (UID: {user_message_instance.uid}) in chat {chat.uid}.")

            if not chat_has_title:
                 active_messages_count = Message.objects.filter(chat_room=chat, is_active=True).count()
                 if active_messages_count == 1:
                    chat.title = (user_input_text[:50].strip() + '...') if len(user_input_text) > 50 else user_input_text.strip()
                    chat.description = (user_input_text[:100].strip() + '...') if len(user_input_text) > 100 else user_input_text.strip()
                    if not chat.title: chat.title = f"Chat {chat.uid[:8]}"
                    if not chat.description: chat.description = f"Chat session {chat.uid[:8]}"
                    chat.save()
                    logger.info(f"Chat title updated to: '{chat.title}'")

            try:
                 all_langchain_history = load_langchain_history_from_db(chat)
                 # ... (resto de la lógica de carga de historial) ...
                 if all_langchain_history and all_langchain_history[-1].type == 'human' and all_langchain_history[-1].content.strip() == user_input_text.strip():
                      agent_user_input_lc_message = all_langchain_history[-1]
                      history_for_agent = all_langchain_history[:-1]
                 else:
                      from langchain.schema import HumanMessage
                      agent_user_input_lc_message = HumanMessage(content=user_input_text)
                      history_for_agent = []
            except Exception as e:
                 logger.error(f"Error loading history: {e}", exc_info=True)
                 from langchain.schema import HumanMessage
                 agent_user_input_lc_message = HumanMessage(content=user_input_text)
                 history_for_agent = []

            agent_input_data = {
                "chat_history": history_for_agent,
                "user_input": agent_user_input_lc_message,
            }

            try:
                logger.info(f"Invoking agent_executor for chat {chat.uid}...")
                result = agent_executor.invoke(agent_input_data)
                logger.info(f"Agent invocation complete for chat {chat.uid}.")
            except NotImplementedError: # Langchain dummy function
                 logger.error("LangChain agent_executor not implemented.", exc_info=True)
                 return Response({"error": "El asistente IA no está disponible."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except Exception as e: # Error real del agente
                logger.error(f"ERROR during LangChain agent execution for chat {chat.uid}: {e}", exc_info=True)
                return Response({"error": f"Hubo un problema al contactar al asistente IA: {str(e)}"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # ... (resto de la lógica de procesamiento de LangChain y guardado de mensaje) ...
            agent_final_text_output = result.get('output', "No se recibió una respuesta válida del asistente.")
            mas_tool_result_dict: Optional[Dict[str, Any]] = None
            if "intermediate_steps" in result and result["intermediate_steps"]:
                for step in result["intermediate_steps"]:
                    action, observation = step
                    tool_name = getattr(action, 'tool', None)
                    if tool_name == "query_historical_data_system":
                        try:
                            mas_tool_result_dict = json.loads(observation)
                        except Exception: # Ser más específico si es posible
                            logger.error(f"Failed to parse tool observation: {observation}", exc_info=True)
                        break
            mas_image_path_from_tool = mas_tool_result_dict.get('image_path') if mas_tool_result_dict else None

            assistant_message_instance = Message(
                chat_room=chat,
                rol=RolType.assistant,
                text_message=agent_final_text_output,
                image=mas_image_path_from_tool,
            )
            assistant_message_instance.save()
            logger.info(f"Assistant message saved (ID: {assistant_message_instance.uid}).")

            response_serializer = self.serializer_class(assistant_message_instance)
            return Response({"message": response_serializer.data}, status=status.HTTP_201_CREATED)

        # Las excepciones Http404, ValidationError, PermissionDenied son manejadas por DRF
        # o por las llamadas a get_object_or_404 e is_valid(raise_exception=True)
        # No es necesario capturarlas explícitamente aquí si confías en el comportamiento de DRF.
        # except Chat.DoesNotExist: # Ya no es necesario si get_object_or_404 se usa con el filtro
        #      logger.warning(f"Chat not found in POST MessageCreateAV for UID: {chat_uid}", exc_info=True)
        #      return Response({"error": "Chat no encontrado o no tienes permiso."}, status=status.HTTP_404_NOT_FOUND)
        except Http404: # Si get_object_or_404 falla
             logger.warning(f"Chat not found (or no permission) in POST MessageCreateAV for UID: {chat_uid}", exc_info=False) # No imprimir traceback para 404
             return Response({"error": "Chat no encontrado o no tienes permiso de acceso."}, status=status.HTTP_404_NOT_FOUND)
        except (PermissionDenied, ValidationError) as e: # DRF las maneja, pero por si acaso
            logger.warning(f"DRF Validation/Permission error in POST MessageCreateAV: {e.detail if hasattr(e, 'detail') else e}", exc_info=False)
            return Response({"error": e.detail if hasattr(e, 'detail') else str(e)}, status=getattr(e, 'status_code', status.HTTP_400_BAD_REQUEST))
        except NotImplementedError: # De Langchain si el setup global falló, pero ya se chequea arriba
             logger.error("LangChain component not implemented in POST MessageCreateAV.", exc_info=True)
             return Response({"error": "El asistente IA no está disponible."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"CRITICAL ERROR in POST MessageCreateAV for chat {chat_uid}: {e.__class__.__name__} - {e}", exc_info=True)
            return Response({"error": "Ocurrió un error inesperado del servidor."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MessageInteractionAV(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        message_uid = request.data.get('message_uid')
        is_like = request.data.get('is_like', True)

        if not message_uid:
            return Response({"error": "message_uid is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # get_object_or_404 lanza Http404, que DRF convierte a una respuesta 404.
            message = get_object_or_404(Message, uid=message_uid)
            # Opcional: if message.chat_room.registered_by != request.user: raise PermissionDenied(...)

            message.update_weight(is_like)
            return Response({"detail": "Interaction recorded successfully."}, status=status.HTTP_200_OK)

        # except Message.DoesNotExist: # Redundante si se usa get_object_or_404
        #     return Response({"error": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        except Http404:
            logger.warning(f"Message not found in MessageInteractionAV for UID: {message_uid}")
            return Response({"error": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        except AttributeError:
             logger.error(f"Message model (UID: {message_uid}) does not have 'update_weight' method.", exc_info=True)
             return Response({"error": "Interaction feature not available for this message."}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            logger.error(f"Error during message interaction: {e.__class__.__name__} - {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred during interaction."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)