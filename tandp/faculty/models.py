from django.db import models
from tpo.models import *
from django.conf import settings

# Create your models here.

class Faculty(models.Model):
    custom_user = models.OneToOneField(
        'tpo.CustomUser', 
        on_delete=models.CASCADE,
        primary_key=True
    )
    full_name = models.CharField(max_length=150)
    department = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    profile_picture = models.ImageField(upload_to="faculty_pictures/", null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.department})"
