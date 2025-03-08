from django.contrib import admin
from django.db.models import Q

from .models import *


def get_meter_types():
    return ContentType.objects.filter(
        Q(app_label='ContactEnergy', model__in=['contactenergymeter'])
        # | Q(app_label='app2', model__in=['model3', 'model4'])
    )


# Register your models here.
@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "provider":
            kwargs["queryset"] = get_meter_types()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    list_display = ('provider', 'meter_id', 'get_content_object_name')

    def get_content_object_name(self, obj):
        if obj.content_object:
            return f"{obj.provider.app_label}, {obj.content_object}"
        else:
            return ''

    get_content_object_name.short_description = "Object"


@admin.register(ContentType)
class ContentTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = ['meter', 'time_slot', 'value']
    list_filter = ['meter', 'time_slot']
    search_fields = ['time_slot']
