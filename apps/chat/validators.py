#apps/chat/validators.py

from pydantic import ValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied

from .models import Chat

class ChatValidators:
    def validate(self, request, chat: Chat):
        """
        Valida que el chat esté activo y pertenezca al usuario.
        Lanza excepciones de DRF si la validación falla.
        """
        if not chat.is_active:
            # Lanza una excepción de DRF que se convertirá en una respuesta 400
            raise ValidationError({"error": "This chat is inactive."}, code=status.HTTP_400_BAD_REQUEST)

        # Importante: Asegúrate de que request.user esté disponible y sea el usuario correcto
        # Esto ya está manejado por IsAuthenticated, pero la lógica de validación refuerza
        if not request.user or not request.user.is_authenticated:
             # Esto no debería pasar con IsAuthenticated, pero como capa extra
             raise PermissionDenied({"error": "Authentication required."})

        if not chat.registered_by == request.user:
            # Lanza una excepción de DRF que se convertirá en una respuesta 403
            raise PermissionDenied({"error": "You are not authorized to access this chat."})

        # Si todo es válido, simplemente retorna True o None.
        # El valor retornado no se usa si no se lanza excepción.
        return True

    def validate_name_chat(self, request, chat: Chat):
        """
        Valida si el chat tiene mensajes activos para ponerle título.
        Lanza excepciones de DRF si la validación falla.
        """
        if not chat.is_active:
            # Lanza excepción en lugar de devolver Response
            raise ValidationError({"error": "This chat is inactive."}, code=status.HTTP_400_BAD_REQUEST)
        if not chat.registered_by == request.user:
            # Lanza excepción en lugar de devolver Response
            raise PermissionDenied({"error": "You are not authorized to access this chat."}, code=status.HTTP_403_FORBIDDEN)
        messages = chat.chat_messages.filter(is_active=True)
        if not messages.exists():
            # Si no hay mensajes, lanzamos una excepción indicando que no se puede nombrar aún
            # O podrías simplemente devolver False y que la lógica que llama lo maneje.
            # Si este validador es para la lógica de poner título, devolver False es más lógico
            # que lanzar una excepción grave. Vamos a mantener que devuelve False/True.
            return False # Mantener este comportamiento si el propósito es solo verificar estado

        return True 