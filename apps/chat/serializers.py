from rest_framework import serializers
from .models import Chat, Message
from apps.utils.serializers import AbstractBaseSerializer
from django.contrib.auth import get_user_model

class MessageSerializer(AbstractBaseSerializer):
    chat_room = serializers.PrimaryKeyRelatedField(queryset=Chat.objects.all(), required=False)
    
    class Meta:
        model = Message
        fields = AbstractBaseSerializer.Meta.fields + [
            "text_message",
            "rol",
            "chat_room",
            "image"
        ]
        extra_kwargs = {
            'rol': {'required': False},
            'chat_room': {'required': False},
            'image': {'required': False}
        }


class ChatSerializer(AbstractBaseSerializer):
    registered_by = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all(), required=False)
    registered_by_username = serializers.CharField(source="registered_by.username", required=False)
    
    class Meta:
        model = Chat
        fields = AbstractBaseSerializer.Meta.fields + [
            "title",
            "description",
            "registered_by",
            "registered_by_username",
        ]
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["registered_by"] = str(representation["registered_by"])
        return representation
    
class ChatDetailSerializer(AbstractBaseSerializer):
    registered_by = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all(), required=False)
    registered_by_username = serializers.CharField(source="registered_by.username", required=False)
    chat_messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Chat
        fields = AbstractBaseSerializer.Meta.fields + [
            "title",
            "description",
            "registered_by",
            "registered_by_username",
            "chat_messages"
        ]
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["registered_by"] = str(representation["registered_by"])
        return representation