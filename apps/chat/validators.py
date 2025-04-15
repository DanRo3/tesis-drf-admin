from rest_framework.response import Response
from rest_framework import status

from .models import Chat

class ChatValidators:
    def validate(self, request, chat: Chat):
        if not chat.is_active:
            return Response(
                {"error": "This chat is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not chat.registered_by == request.user:
            return Response(
                {"error": "You are not authorized to access this chat."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None  # Importante: devuelve None si la validación es exitosa

    def validate_name_chat(self, request, chat: Chat):
        if not chat.is_active:
            return Response(
                {"error": "This chat is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not chat.registered_by == request.user:
            return Response(
                {"error": "You are not authorized to access this chat."},
                status=status.HTTP_403_FORBIDDEN,
            )
        messages = chat.chat_messages.filter(is_active=True)
        if not messages.exists():
            return False
        return True