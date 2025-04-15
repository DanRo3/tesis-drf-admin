from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.files.base import ContentFile
from apps.chat.validators import ChatValidators
from apps.utils.paginations import MediumSetPagination
from apps.utils.enums import RolType
from .models import Chat, Message
from rest_framework import serializers
from .serializers import ChatSerializer, ChatDetailSerializer, MessageSerializer
import base64
import json
import traceback 

# --- LangChain Integration Imports ---
# Attempt to import necessary components from your LangChain setup file
# Replace 'apps.chat.langchain_setup' with the actual Python path to your setup file
try:
    from apps.chat.langchain_setup import (
        agent_executor,                # The core LangChain agent executor
        load_langchain_history_from_db # Your function to load history
    )
    LANGCHAIN_SETUP_SUCCESSFUL = True
    print("INFO: LangChain setup loaded successfully.")
except ImportError as e:
    print(f"ERROR: Failed to import LangChain setup: {e}. AI assistant features will be disabled.")
    # Define dummy functions to prevent runtime errors if import fails
    def agent_executor(*args, **kwargs):
        raise NotImplementedError("LangChain agent_executor is not available due to import failure.")
    def load_langchain_history_from_db(*args, **kwargs):
        raise NotImplementedError("LangChain history loader is not available due to import failure.")
    LANGCHAIN_SETUP_SUCCESSFUL = False
except Exception as e:
    # Catch any other unexpected error during import/setup
    print(f"ERROR: An unexpected error occurred during LangChain setup import: {e}")
    print(traceback.format_exc()) # Print full traceback for debugging
    # Define dummy functions
    def agent_executor(*args, **kwargs): raise NotImplementedError("LangChain agent_executor unavailable.")
    def load_langchain_history_from_db(*args, **kwargs): raise NotImplementedError("LangChain history loader unavailable.")
    LANGCHAIN_SETUP_SUCCESSFUL = False

def handle_exceptions(func):
        """
        Decorator to handle common exceptions in Chat views.
        (Your existing decorator code)
        """
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Chat.DoesNotExist:
                return Response(
                    {"error": "Chat data not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            except ValueError as e:
                # Example: Handle potential validation errors if needed
                return Response(
                    {"error": f"Value error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                # Generic fallback for unexpected errors
                print(f"Unhandled exception in ChatViewSet: {e}") # Log the error
                print(traceback.format_exc())
                return Response(
                    {"error": "An unexpected server error occurred."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return wrapper



class ChatViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows chat sessions to be viewed or edited.
    """
    queryset = Chat.objects.filter(is_active=True) # Simplified queryset
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]

    # Only list chats belonging to the requesting user
    @handle_exceptions
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().filter(registered_by=request.user).order_by('-created_at')
        paginator = MediumSetPagination() # Use your pagination class
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_queryset, many=True)
        return paginator.get_paginated_response({"chats": serializer.data})

    # Create a new chat session for the user
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Ensure the chat is associated with the logged-in user
        serializer.save(registered_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Retrieve details of a specific chat (including messages via serializer)
    @handle_exceptions
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Ensure the user requesting the chat is the one who registered it
        if instance.registered_by != request.user:
             return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ChatDetailSerializer(instance) # Assumes this serializer includes messages
        return Response({"chat": serializer.data}, status=status.HTTP_200_OK)

    # Soft delete a chat session
    @handle_exceptions
    def destroy(self, request, *args, **kwargs):
        instance_chat = self.get_object()
        # Ensure the user deleting the chat is the one who registered it
        if instance_chat.registered_by != request.user:
             return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        if not instance_chat.is_active:
            return Response(
                {"detail": "This chat is already inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance_chat.soft_delete() # Assumes this method sets is_active=False and saves
        return Response(
            {"message": "Chat deleted successfully"},
            status=status.HTTP_204_NO_CONTENT, # Standard for successful delete with no body
        )


# --- Message Creation and AI Response View ---
# Handles receiving new user messages and generating AI responses using LangChain.
class MessageCreateAV(APIView):
    """
    API endpoint to post new messages to a chat and get AI responses.
    Also allows retrieving the message history for a chat.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    chat_validator = ChatValidators() # Instantiate your validator

    def get(self, request, *args, **kwargs):
        """
        Retrieve the message history for a specific chat.
        """
        chat_uid = kwargs.get('pk')
        if not chat_uid:
             return Response({"error": "Chat UID not provided in URL."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            chat = get_object_or_404(Chat, uid=chat_uid)
            # Validate user permission to access this chat
            self.chat_validator.validate(chat=chat, request=request) # Assumes this raises exceptions on failure

            # Retrieve active messages ordered by creation time
            queryset = Message.objects.filter(chat_room=chat, is_active=True).order_by('created_at')
            serializer = self.serializer_class(queryset, many=True)
            return Response({"history": serializer.data}, status=status.HTTP_200_OK)

        except Chat.DoesNotExist:
             return Response({"error": "Chat not found."}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as e: # Assuming your validator might raise this
             return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            print(f"Error in GET MessageCreateAV: {e}")
            print(traceback.format_exc())
            return Response({"error": "An unexpected error occurred retrieving history."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        """
        Receive a user message, save it, invoke the LangChain agent for a response,
        process the response (including potential external tool results like images),
        save the assistant's message, and return it.
        """
        # Check if LangChain components were loaded successfully at startup
        if not LANGCHAIN_SETUP_SUCCESSFUL:
             return Response(
                 {"error": "El asistente IA no está disponible actualmente debido a un problema de configuración."},
                 status=status.HTTP_503_SERVICE_UNAVAILABLE # Service Unavailable
             )

        chat_uid = kwargs.get('pk')
        if not chat_uid:
             return Response({"error": "Chat UID not provided in URL."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            chat = get_object_or_404(Chat, uid=chat_uid)
            chat_validator = ChatValidators() # Instancia tu validador
            response = chat_validator.validate(request, chat)  # Pasa el request directamente
            if response:
                return response  # Devuelve la respuesta de error si la validación falla # Asume que esto lanza excepciones en caso de fallo
            chat_has_title = bool(chat.title)

            # 1. Validate and Save User Message
            serializer = self.serializer_class(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            user_message_instance = Message.objects.create(
                chat_room=chat,
                rol=RolType.user, # Use your Enum
                text_message=serializer.validated_data.get('text_message', ''),
                image=serializer.validated_data.get('image', None), # Handle potential image upload
            )
            user_input_text = user_message_instance.text_message

            # 2. Update Chat Title if it's the first message
            if not chat_has_title and user_input_text:
                chat.title = user_input_text[:30] # Slightly longer default title
                chat.description = user_input_text[:60] # Slightly longer default description
                chat.save()

            # 3. Load History using LangChain Formatter
            try:
                 # Call the imported function to get history in LangChain Message format
                 langchain_history = load_langchain_history_from_db(chat)
            except Exception as e:
                 print(f"Error loading history via load_langchain_history_from_db: {e}")
                 print(traceback.format_exc())
                 return Response({"error": "Error procesando el historial del chat."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 4. Prepare Input for the LangChain Agent
            # Determine the actual input content based on the last message saved
            if langchain_history and langchain_history[-1].type == 'human':
                 agent_user_input = langchain_history[-1].content
                 # Pass history *excluding* the latest user message which goes into 'user_input'
                 history_for_agent = langchain_history[:-1]
            else:
                 # Fallback scenario (e.g., first message, or unexpected history)
                 # Construct the input from the current message instance
                 # (This part might need refinement based on how load_langchain_history_from_db handles images)
                 agent_user_input = user_input_text # Simplification: assumes text only for fallback
                 history_for_agent = langchain_history # Pass history as is

            agent_input_data = {
                "chat_history": history_for_agent,
                "user_input": agent_user_input,
            }

            # 5. Invoke the LangChain Agent
            try:
                # Call the imported agent executor instance
                print(f"Invoking agent for chat {chat.uid}...") # Log agent invocation
                result = agent_executor.invoke(agent_input_data)
                print(f"Agent invocation complete for chat {chat.uid}.") # Log completion

            except NotImplementedError: # If LangChain setup failed initially
                 return Response({"error": "El asistente IA no está disponible."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except Exception as e:
                # Catch errors during agent execution (API errors, timeouts, etc.)
                print(f"ERROR during LangChain agent execution for chat {chat.uid}: {e}")
                print(traceback.format_exc())
                # Provide a user-friendly error message
                return Response({"error": f"Hubo un problema al contactar al asistente IA: {str(e)}"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 6. Process Agent Response and Potential Tool Output
            agent_final_text = result.get('output', "No se recibió una respuesta válida del asistente.")
            mas_base64_image = None # To store potential image from the MAS tool

            # Check if the specialized MAS tool was called by the agent
            if "intermediate_steps" in result and result["intermediate_steps"]:
                print(f"Agent for chat {chat.uid} used tools: {len(result['intermediate_steps'])} step(s).")
                for step in result["intermediate_steps"]:
                    action, observation = step # observation should be the JSON string from our tool
                    tool_name = getattr(action, 'tool', None)

                    # Check if the specific MAS tool was called
                    if tool_name == "query_historical_data_system":
                        print(f"Processing result from tool '{tool_name}' for chat {chat.uid}...")
                        try:
                            # Parse the JSON string returned by the tool
                            mas_response_dict = json.loads(observation)
                            mas_base64_image = mas_response_dict.get('image_response') # Extract image (if any)
                            mas_error = mas_response_dict.get('error') # Extract error (if any)
                            mas_text = mas_response_dict.get('text_response') # Extract text (if any)

                            # Optionally append MAS info/error to the agent's main text response
                            if mas_error:
                                agent_final_text += f"\n\n[Nota del Sistema de Datos Históricos: {mas_error}]"
                                print(f"MAS tool reported error for chat {chat.uid}: {mas_error}")
                            elif mas_text and mas_text not in agent_final_text:
                                # Avoid appending if agent likely already incorporated it
                                # This logic might need refinement based on agent's behavior
                                # agent_final_text += f"\n\n[Info. Sistema Datos: {mas_text}]"
                                pass

                            if mas_base64_image:
                                print(f"MAS tool returned an image for chat {chat.uid}.")

                        except json.JSONDecodeError:
                            print(f"ERROR: Failed to decode JSON from MAS tool observation for chat {chat.uid}: {observation}")
                            agent_final_text += "\n\n[Nota: Hubo un problema técnico al procesar datos externos.]"
                        except Exception as e:
                            print(f"ERROR processing MAS tool result for chat {chat.uid}: {e}")
                            print(traceback.format_exc())
                            agent_final_text += f"\n\n[Nota: Error inesperado al procesar datos externos: {str(e)}]"
                        # break # Assuming only one MAS tool call needed per turn

            # 7. Save the Final Assistant Message to Database
            assistant_message_instance = Message(
                chat_room=chat,
                rol=RolType.assistant, # Use your Enum
                text_message=agent_final_text, # The final text, potentially annotated
                # Intentionally do not assign registered_by for assistant messages,
                # or assign a specific system user if you have one.
                # registered_by=request.user # Probably incorrect for assistant message
            )

            # Handle image saving if provided by the MAS tool
            if mas_base64_image:
                try:
                    # Expecting format "data:image/png;base64,..."
                    if ";base64," in mas_base64_image:
                        header, encoded_data = mas_base64_image.split(",", 1)
                        image_data = base64.b64decode(encoded_data)
                        # Determine filename (improve by checking header if possible)
                        mime_type = header.split(':')[1].split(';')[0] # e.g., 'image/png'
                        extension = mime_type.split('/')[-1] # e.g., 'png'
                        filename = f"mas_visualization_{chat.uid[:8]}.{extension}" # Unique-ish filename

                        django_image_file = ContentFile(image_data, name=filename)
                        assistant_message_instance.image = django_image_file
                        print(f"Image from MAS saved for message in chat {chat.uid}.")
                    else:
                        print(f"WARN: Unexpected base64 image format from MAS for chat {chat.uid}.")
                        assistant_message_instance.text_message += "\n[Nota: Imagen recibida con formato inesperado.]"
                except (ValueError, TypeError, base64.binascii.Error) as e:
                    print(f"ERROR decoding/saving base64 image from MAS for chat {chat.uid}: {e}")
                    assistant_message_instance.text_message += "\n[Nota: Error al procesar la imagen recibida.]"
                except Exception as e:
                    print(f"ERROR saving image file for chat {chat.uid}: {e}")
                    print(traceback.format_exc())
                    assistant_message_instance.text_message += "\n[Nota: Error al guardar la imagen recibida.]"


            assistant_message_instance.save()
            print(f"Assistant message saved (ID: {assistant_message_instance.uid}) for chat {chat.uid}.")

            # 8. Serialize and Return the Saved Assistant Message
            response_serializer = self.serializer_class(assistant_message_instance)
            return Response({"message": response_serializer.data}, status=status.HTTP_201_CREATED)

        # Catch specific exceptions from validation or object retrieval first
        except Chat.DoesNotExist:
             return Response({"error": "Chat not found."}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as e: # If your validator raises this
             return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        # Catch DRF validation errors if is_valid(raise_exception=True) is used
        except serializers.ValidationError as e:
             return Response({"error": "Invalid input data.", "details": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        # Generic fallback for other unexpected errors in the POST method
        except Exception as e:
            print(f"CRITICAL ERROR in POST MessageCreateAV for chat {kwargs.get('pk')}: {e}")
            print(traceback.format_exc())
            return Response({"error": "An unexpected server error occurred while processing your message."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- Message Interaction View ---
# Handles non-AI interactions like liking/disliking messages. No LangChain logic here.
class MessageInteractionAV(APIView):
    """
    API endpoint to handle user interactions with specific messages (e.g., like/dislike).
    """
    permission_classes = [IsAuthenticated] # Ensure user is logged in

    def post(self, request, *args, **kwargs):
        message_uid = request.data.get('message_uid')
        is_like = request.data.get('is_like', True) # Default to 'like' interaction

        if not message_uid:
            return Response({"error": "message_uid is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Find the message
            message = get_object_or_404(Message, uid=message_uid)

            # Optional: Add validation - Can the user interact with this message?
            # (e.g., does the message belong to a chat the user owns?)
            # if message.chat_room.registered_by != request.user:
            #    return Response({"error": "Forbidden to interact with this message."}, status=status.HTTP_403_FORBIDDEN)

            # Assuming your Message model has an 'update_weight' method
            message.update_weight(is_like) # Call your model method

            return Response({"detail": "Interaction recorded successfully."}, status=status.HTTP_200_OK)

        except Message.DoesNotExist:
            return Response({"error": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        except AttributeError:
             # If the 'update_weight' method doesn't exist on the model
             print(f"ERROR: Message model (UID: {message_uid}) does not have 'update_weight' method.")
             return Response({"error": "Interaction feature not available for this message."}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            print(f"Error during message interaction: {e}")
            print(traceback.format_exc())
            return Response({"error": "An unexpected error occurred during interaction."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


 