import json
import uuid
from unittest.mock import patch, MagicMock

from django.urls import reverse
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from apps.chat.models import Chat, Message
from apps.utils.enums import RolType

User = get_user_model()

def create_test_user(username="testuser", password="testpassword", email=None):
    if email is None:
        email = f"{username.lower().replace(' ', '').replace('_', '')}@example.com"
    return User.objects.create_user(username=username, email=email, password=password)

class ChatViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = create_test_user(username="user1_chat_tests")
        self.user2 = create_test_user(username="user2_chat_tests")
        self.client.force_authenticate(user=self.user1)

        self.chat1_user1 = Chat.objects.create(registered_by=self.user1, title="Chat 1 User 1")
        self.chat2_user1_inactive = Chat.objects.create(registered_by=self.user1, title="Chat 2 User 1 Inactive", is_active=False)
        self.chat1_user2 = Chat.objects.create(registered_by=self.user2, title="Chat 1 User 2")

    def test_list_chats_for_authenticated_user(self):
        url = reverse("chats-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        listed_chats = None
        if "results" in response.data and isinstance(response.data["results"], dict) and "chats" in response.data["results"]:
            listed_chats = response.data["results"]["chats"]
        elif "chats" in response.data and isinstance(response.data["chats"], list):
             listed_chats = response.data["chats"]
        else:
            self.fail(f"La estructura de paginación esperada no se encontró. Respuesta: {response.data}")

        self.assertEqual(len(listed_chats), 1)
        self.assertEqual(listed_chats[0]["title"], self.chat1_user1.title)

    def test_list_chats_unauthenticated(self):
        self.client.logout()
        url = reverse("chats-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_chat_success(self):
        url = reverse("chats-list")
        data = {"title": "New Test Chat by User1"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Chat.objects.count(), 4)
        new_chat = Chat.objects.get(title="New Test Chat by User1")
        self.assertEqual(new_chat.registered_by, self.user1)
        self.assertEqual(response.data["title"], "New Test Chat by User1")

    def test_retrieve_chat_owner_success(self):
        url = reverse("chats-detail", kwargs={"pk": self.chat1_user1.uid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["chat"]["title"], self.chat1_user1.title)

    def test_retrieve_chat_not_owner_forbidden(self):
        url = reverse("chats-detail", kwargs={"pk": self.chat1_user2.uid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_chat_not_found(self):
        non_existent_uid = uuid.uuid4()
        url = reverse("chats-detail", kwargs={"pk": non_existent_uid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_destroy_chat_owner_success(self):
        url = reverse("chats-detail", kwargs={"pk": self.chat1_user1.uid})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.chat1_user1.refresh_from_db()
        self.assertFalse(self.chat1_user1.is_active)

    def test_destroy_chat_not_owner_forbidden(self):
        url = reverse("chats-detail", kwargs={"pk": self.chat1_user2.uid})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.chat1_user2.refresh_from_db()
        self.assertTrue(self.chat1_user2.is_active)

    def test_destroy_chat_already_inactive(self):
        url = reverse("chats-detail", kwargs={"pk": self.chat2_user1_inactive.uid})
        response = self.client.delete(url)
        # Si el queryset base es filter(is_active=True), un chat inactivo no se encontrará.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Si quisieras probar la lógica del 400, necesitarías un chat que sea activo,
        # luego inactivarlo, y LUEGO intentar el GET/DELETE para que self.get_object()
        # lo encuentre pero la lógica de 'is_active' aplique.
        # O modificar el queryset base del ViewSet para incluir inactivos,
        # y que el filtro de 'is_active' se haga más adelante.


class MessageCreateAVTests(APITestCase):
    def setUp(self):
        self.user = create_test_user(username="user_message_tests")
        self.client.force_authenticate(user=self.user)

        self.chat = Chat.objects.create(registered_by=self.user, title="Test Chat for Messages")
        self.other_user_for_messages = create_test_user(username="otheruser_message_tests")
        self.other_chat_for_messages = Chat.objects.create(registered_by=self.other_user_for_messages, title="Other User's Chat for Messages")

        Message.objects.create(chat_room=self.chat, rol=RolType.user, text_message="Hello")
        Message.objects.create(chat_room=self.chat, rol=RolType.assistant, text_message="Hi there!")

        self.messages_url = reverse("chat-messages", kwargs={"pk": self.chat.uid})

    def test_get_message_history_success(self):
        response = self.client.get(self.messages_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["history"]), 2)
        self.assertEqual(response.data["history"][0]["text_message"], "Hello")

    def test_get_message_history_chat_not_found(self):
        non_existent_uid = uuid.uuid4()
        url = reverse("chat-messages", kwargs={"pk": non_existent_uid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_message_history_not_owner(self):
        url = reverse("chat-messages", kwargs={"pk": self.other_chat_for_messages.uid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.chat.views.LANGCHAIN_SETUP_SUCCESSFUL', True)
    @patch('apps.chat.views.agent_executor')
    @patch('apps.chat.views.load_langchain_history_from_db')
    def test_post_message_success_first_message_updates_chat_title(self, mock_load_history, mock_agent_executor):
        new_chat = Chat.objects.create(registered_by=self.user)
        self.assertEqual(Message.objects.filter(chat_room=new_chat).count(), 0)

        mock_load_history.return_value = []
        mock_agent_executor.invoke.return_value = {"output": "AI response!"}

        url = reverse("chat-messages", kwargs={"pk": new_chat.uid})
        user_input_text = "This is the very first message in this new chat." # 46 chars
        data = {"text_message": user_input_text}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # ... (resto de las aserciones del test) ...
        new_chat.refresh_from_db()
        
        # Lógica de la vista para el título:
        if len(user_input_text) > 50:
            expected_title = user_input_text[:50].strip() + '...'
        else:
            expected_title = user_input_text.strip()
        
        self.assertEqual(new_chat.title, expected_title)
        self.assertIsNotNone(new_chat.description)


    @patch('apps.chat.views.LANGCHAIN_SETUP_SUCCESSFUL', True)
    @patch('apps.chat.views.agent_executor')
    @patch('apps.chat.views.load_langchain_history_from_db')
    def test_post_message_success_with_tool_image_path(self, mock_load_history, mock_agent_executor):
        # Crear un chat nuevo para este test para evitar interferencias con mensajes del setUp
        test_chat_for_tool = Chat.objects.create(registered_by=self.user, title="Chat for Tool Test")
        url_for_tool_test = reverse("chat-messages", kwargs={"pk": test_chat_for_tool.uid})

        mock_load_history.return_value = []
        tool_output_json = json.dumps({
            "image_path": "/media/generated_images/some_image.png",
            "text_response": "Here is the data and an image.",
            "error": None
        })
        mock_action = MagicMock()
        mock_action.tool = "query_historical_data_system"
        mock_agent_executor.invoke.return_value = {
            "output": "AI final response based on tool.",
            "intermediate_steps": [(mock_action, tool_output_json)]
        }

        data = {"text_message": "User asks for image"}
        response = self.client.post(url_for_tool_test, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ai_message = Message.objects.filter(chat_room=test_chat_for_tool, rol=RolType.assistant).latest('created_at')
        self.assertEqual(ai_message.image, "/media/generated_images/some_image.png")
        self.assertEqual(response.data["message"]["text_message"], "AI final response based on tool.")

    @patch('apps.chat.views.LANGCHAIN_SETUP_SUCCESSFUL', False)
    def test_post_message_langchain_setup_failed(self):
        data = {"text_message": "Hello AI"}
        response = self.client.post(self.messages_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("el asistente ia no está disponible actualmente debido a un problema de configuración.", response.data["error"].lower())

    @patch('apps.chat.views.LANGCHAIN_SETUP_SUCCESSFUL', True)
    @patch('apps.chat.views.agent_executor')
    def test_post_message_agent_executor_notimplemented_error(self, mock_agent_executor):
        mock_agent_executor.invoke.side_effect = NotImplementedError("Agent not ready")
        data = {"text_message": "Hello AI"}
        response = self.client.post(self.messages_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch('apps.chat.views.LANGCHAIN_SETUP_SUCCESSFUL', True)
    @patch('apps.chat.views.agent_executor')
    def test_post_message_agent_executor_generic_exception(self, mock_agent_executor):
        mock_agent_executor.invoke.side_effect = Exception("Something went wrong in agent")
        data = {"text_message": "Hello AI"}
        response = self.client.post(self.messages_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("hubo un problema al contactar al asistente ia", response.data["error"].lower())

    def test_post_message_invalid_data_serializer_error(self):
        data = {} # Datos vacíos, text_message es requerido
        response = self.client.post(self.messages_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("text_message", response.data["error"]) # Acceder al campo específico del error

    def test_post_message_chat_not_found(self):
        non_existent_uid = uuid.uuid4()
        url = reverse("chat-messages", kwargs={"pk": non_existent_uid})
        data = {"text_message": "Test"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_message_to_other_user_chat_forbidden(self):
        url = reverse("chat-messages", kwargs={"pk": self.other_chat_for_messages.uid})
        data = {"text_message": "Trying to post here"}
        response = self.client.post(url, data, format="json")
        # La vista MessageCreateAV.post usa:
        # get_object_or_404(Chat.objects.filter(registered_by=request.user, is_active=True), uid=chat_uid)
        # Esto devolverá un 404 si el chat no pertenece al request.user
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MessageInteractionAVTests(APITestCase):
    def setUp(self):
        self.user = create_test_user(username="user_interaction_tests")
        self.client.force_authenticate(user=self.user)

        self.chat = Chat.objects.create(registered_by=self.user)
        self.message_to_interact = Message.objects.create(
            chat_room=self.chat,
            rol=RolType.assistant,
            text_message="Interact with me!"
        )
        self.interaction_url = reverse("chat-interaction", kwargs={"chat_uid": self.chat.uid})

    @patch('apps.chat.models.Message.update_weight')
    def test_like_message_success(self, mock_update_weight):
        data = {"message_uid": str(self.message_to_interact.uid), "is_like": True}
        response = self.client.post(self.interaction_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Interaction recorded successfully.")
        mock_update_weight.assert_called_once_with(True)

    @patch('apps.chat.models.Message.update_weight')
    def test_dislike_message_success(self, mock_update_weight):
        data = {"message_uid": str(self.message_to_interact.uid), "is_like": False}
        response = self.client.post(self.interaction_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_update_weight.assert_called_once_with(False)

    def test_interact_message_uid_required(self):
        data = {"is_like": True}
        response = self.client.post(self.interaction_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message_uid is required", response.data["error"])

    def test_interact_message_not_found(self):
        non_existent_uid = uuid.uuid4()
        data = {"message_uid": str(non_existent_uid), "is_like": True}
        response = self.client.post(self.interaction_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("message not found", response.data["error"].lower())

    @patch('apps.chat.views.get_object_or_404')
    def test_interact_message_model_missing_update_weight(self, mock_get_object_or_404_in_view):
        mock_message_instance = MagicMock(spec=Message)
        mock_message_instance.update_weight = MagicMock(side_effect=AttributeError("Mocked message has no update_weight"))
        mock_get_object_or_404_in_view.return_value = mock_message_instance

        data = {"message_uid": str(self.message_to_interact.uid), "is_like": True}
        response = self.client.post(self.interaction_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertIn("interaction feature not available", response.data["error"].lower())
        mock_get_object_or_404_in_view.assert_called_once_with(Message, uid=str(self.message_to_interact.uid))