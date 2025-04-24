from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(CustomUser)
admin.site.register(TPO)
admin.site.register(Company)
admin.site.register(Eligibility)
admin.site.register(Notification)
admin.site.register(StudentData)
admin.site.register(PlacementOffer)
