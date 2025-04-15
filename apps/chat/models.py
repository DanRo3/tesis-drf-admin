from django.db import models
from django.utils.translation import gettext_lazy as _ 
from apps.utils.models import BaseModel
from apps.utils.enums import RolType
from django.contrib.auth.models import User

# Create your models here.

class Chat(BaseModel):

    title = models.CharField(_("Title"), max_length=255, null=True, blank=True, default=_("New Chat"),
                                help_text=_("Title of the chat room"),
                            )
    description = models.TextField(_("Description"), help_text=_("Description of the chat room"),
                                    null=True, blank=True,
                                )
    registered_by = models.ForeignKey(User, verbose_name=_("Created By"), on_delete=models.CASCADE,
                                        related_name="registered_chats",
                                    )

    class Meta:
        verbose_name = _("Chat")
        verbose_name_plural = _("Chats")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title



class Message(BaseModel):

    text_message = models.TextField(_("Text Message"), help_text=_("Text message of the chat"),
                                    null=False, blank=False,
                                )
    chat_room = models.ForeignKey(Chat, verbose_name=_("Chat Room"), on_delete=models.CASCADE,
                                    help_text=_("Chat room where the message was created"),
                                    related_name="chat_messages", null=False, blank=False
                                )
    rol = models.CharField(_("Rol"), max_length=50, help_text=_("Message Rol"), choices=RolType.choices,)
    image = models.ImageField(_("Image"), upload_to="chat_images/", null=True, blank=True,
                                help_text=_("Image of the message"),
                            )
    weight = models.IntegerField(_("Weight"), help_text=_("Weight of the message"), null=True, blank=True,
                                    default=1,   
                                )

    class Meta:
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        ordering = ["created_at"]

    def __str__(self):
        return str(_(f"Created Message with uid {self.uid}"))

    def update_weight(self, is_like):
        if is_like == "True":
            self.weight = 2
        else:
            self.weight = 0
        self.save()



