from django.contrib import admin

from ContactEnergy.models import ContactEnergyMeter


# Register your models here.
@admin.register(ContactEnergyMeter)
class ContactEnergyMeterAdmin(admin.ModelAdmin):
    pass
