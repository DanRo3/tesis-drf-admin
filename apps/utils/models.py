from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _ 
import uuid
# Create your models here.
class AbstractDateModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created Date"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated Date"))
    
    class Meta:
        abstract = True

class BaseModel(AbstractDateModel):
    """
    model that represents the basic fields for all instances of the database
    """
    uid = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    slug = models.SlugField(unique=True, blank=True, null=True,verbose_name=_("Slug"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    class Meta:
        abstract = True

    def soft_delete(self):
        """Logically remove the object by changing is_active to False."""
        self.is_active = False
        self.save()
        
class CustomUser(AbstractUser):
    """
    Custom user model where email is unique and required.
    """
    email = models.EmailField(_('email address'), unique=True)

    def __str__(self):
        return self.username