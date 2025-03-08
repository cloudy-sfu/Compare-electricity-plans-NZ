from django.contrib import admin

from Plan.models import ChargingPlan, Price


# Register your models here.
@admin.register(ChargingPlan)
class ChargingPlanAdmin(admin.ModelAdmin):
    list_display = ['company', 'name', 'applied_date', 'daily_fixed_price',
                    'GST_ratio', 'levy', 'default_unit_price']
    list_filter = ['company']
    search_fields = ['company']

@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ['plan', 'unit_price'] + Price.DAYS_OF_WEEK + [
        'time_from', 'time_to']
    list_filter = ['plan']
    search_fields = ['plan__company', 'plan__name', 'plan__applied_date']
