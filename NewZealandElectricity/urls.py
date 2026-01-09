"""
URL configuration for NewZealandElectricity project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from django.urls import path
import ContactEnergy.views as v1
import Meter.views as v2
import Plan.views as v3

urlpatterns = [
    # path('admin/', admin.site.urls),
    path('get_data_contact', v1.contact_energy_login),
    path('get_data_contact/auth', v1.contact_energy_auth),
    path('get_data_contact/account', v1.contact_energy_account),
    path('get_data_contact/usage', v1.contact_energy_usage),
    path('get_data_contact/progress', v1.contact_energy_progress),
    path('', v2.main),
    path('migrate_meters', v2.view_migrate_meters),
    path('migrate_meters/migrate', v2.migrate_meters),
    path('integrity', v2.view_integrity),
    path('integrity/check', v2.check_integrity),
    path('plans', v3.view_plans),
    path('plans/<int:plan_id>', v3.view_change_plan),
    path('plans/change/<int:plan_id>', v3.change_plan),
    path('plans/new', v3.view_add_plan),
    path('plans/add', v3.add_plan),
    path('plans/delete/<int:plan_id>', v3.delete_plan),
    path('prices/<int:price_id>', v3.view_change_price),
    path('prices/change/<int:price_id>', v3.change_price),
    path('prices/new/<int:plan_id>', v3.view_add_price),
    path('prices/add', v3.add_price),
    path('prices/delete/<int:price_id>', v3.delete_price),
    path('meters', v2.view_select_meter),
    path('select_meter', v2.select_meter),
    path('compare', v3.view_compare),
    path('compare/action', v3.compare),
]
