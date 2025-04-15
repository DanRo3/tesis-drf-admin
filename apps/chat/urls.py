from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import ChatViewSet, MessageCreateAV, MessageInteractionAV

router = DefaultRouter()
router.register(r'chats', ChatViewSet, basename='chats')  # Agrega basename

urlpatterns = [
    path('', include(router.urls)),
    path('chats/<uuid:pk>/messages/', MessageCreateAV.as_view(), name='chat-messages'),  # Agregar name
    path('chats/<uuid:chat_uid>/messages/interaction/', MessageInteractionAV.as_view(), name='chat-interaction'),  # Agregar name
]