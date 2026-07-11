from django.shortcuts import render
import json
import time
import uuid
from datetime import datetime, timedelta, date
from random import uniform

import pandas as pd
import pytz
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from requests import Session

from Meter.models import Meter, Usage
from NewZealandElectricity.settings import TIME_ZONE
from . import get_data
from .models import *


# Create your views here.
class MercuryLogin(forms.Form):
    username = forms.EmailField(
        required=True, widget=forms.EmailInput({'class': 'form-control'})
    )
    password = forms.CharField(
        required=True, widget=forms.PasswordInput({'class': 'form-control'})
    )


def validate_end_date(input_date):
    today = datetime.now(tz=pytz.timezone(TIME_ZONE)).date()
    latest_date = today - timedelta(days=3)
    if input_date > latest_date:
        raise ValidationError("The date cannot be later than " + latest_date.strftime("%Y-%m-%d"))


def validate_start_date(input_date):
    # Contact Energy is founded in 1999-04-01.
    earliest_date = date(1999, 4, 1)
    if input_date < earliest_date:
        raise ValidationError("The date cannot be earlier than " + earliest_date.strftime("%Y-%m-%d"))


def mercury_login(req, failed_reason=None):
    return render(req, 'mercury_login.html', {
        "login_form": MercuryLogin(),
        "failed_reason": failed_reason,
    })


@require_POST
def mercury_auth(req):
    login_form = MercuryLogin(req.POST)
    if not login_form.is_valid():
        return mercury_login(req, failed_reason=login_form.errors.as_text())
    username = login_form.cleaned_data.get('username')
    password = login_form.cleaned_data.get('password')

    try:
        token = get_data.login(username, password)
        access_token = token["access_token"]
        ocp_key = token["Ocp-Apim-Subscription-Key"]
        customer_id = get_data.get_customer_id(access_token)
        accounts = get_data.get_accounts(access_token, ocp_key, customer_id)
        for account in accounts:
            account_id = account.get("accountId")
            if account_id:
                services = get_data.get_electricity_services(
                    access_token, ocp_key, customer_id, account_id)
                for service in services:
                    meter, created = MercuryMeter.objects.get_or_create(
                        customer_id=customer_id,
                        account_id=account_id,
                        service_id=service.get("serviceId"),
                        name=account.get("accountName"),
                        address=account.get("billingAddress"),
                        service_start_time=pd.Timestamp(
                            service.get("serviceStartDate"), tz="Pacific/Auckland"),
                    )
                    session = MercurySession(
                        meter=meter,
                        access_token=access_token,
                        ocp_key=ocp_key,
                    )
                    session.save()
    except Exception as e:
        return mercury_login(req, failed_reason=f"{type(e).__name__}: {e}")
    return mercury_account(req)


class MercuryAccount(forms.Form):
    account_and_contract = forms.ModelChoiceField(
        required=True, widget=forms.Select({"class": "form-select", "style": "white-space: normal;"}),
        queryset=MercuryMeter.objects.all(),
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1999-04-01"}),
        validators=[validate_start_date],
        help_text="Optional: the service start date by default. No earlier than 1999-04-01."
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1999-04-01"}),
        validators=[validate_end_date],
        help_text="Optional: 3 days ago by default. No later than 3 days ago."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['account_and_contract'].initial = MercuryMeter.objects.first()
        except (OperationalError, ProgrammingError):
            pass


def mercury_account(req, failed_reason=None, done_signal=False):
    return render(req, 'mercury_account.html', {
        "account_form": MercuryAccount,
        "failed_reason": failed_reason,
        "done_signal": done_signal
    })


def get_missing_dates_in_usage(start_date, end_date, meter):
    start_date_midnight = (pd.to_datetime(start_date)
                           .tz_localize(tz=TIME_ZONE, ambiguous=False))
    end_date_next_midnight = (pd.to_datetime(end_date + pd.Timedelta(days=1))
                              .tz_localize(tz=TIME_ZONE, ambiguous=False))
    existed_dates = Usage.objects.filter(
        time_slot__gte=start_date_midnight,
        time_slot__lt=end_date_next_midnight,
        meter=meter,
    ).annotate(date=TruncDate("time_slot")).values('date').distinct()
    existed_dates = [item['date'] for item in existed_dates]
    all_dates = pd.date_range(start=start_date, end=end_date, freq='1d')
    missing_dates = all_dates.difference(existed_dates)
    return missing_dates


@require_POST
def mercury_usage(req):
    account_form = MercuryAccount(req.POST)
    if not account_form.is_valid():
        return HttpResponse(account_form.errors.as_text(), status=500)
    account_and_contract = account_form.cleaned_data.get('account_and_contract')
    start_date = account_form.cleaned_data.get('start_date')
    end_date = account_form.cleaned_data.get('end_date')
    if (not start_date) or (start_date < account_and_contract.service_start_time):
        start_date = account_and_contract.service_start_time
    if not end_date:
        end_date = pd.Timestamp('now', tz=TIME_ZONE).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    start_date_midnight = (pd.to_datetime(start_date)
                           .tz_localize(tz=TIME_ZONE, ambiguous=False))
    end_date_next_midnight = (pd.to_datetime(end_date + pd.Timedelta(days=1))
                              .tz_localize(tz=TIME_ZONE, ambiguous=False))
    meter, _ = Meter.objects.get_or_create(
        provider=ContentType.objects.get_for_model(MercuryMeter),
        meter_id=account_and_contract.id,
    )
    expiry_time = datetime.now(tz=pytz.timezone(TIME_ZONE)) - timedelta(days=1)
    MercurySession.objects.filter(created_time__lte=expiry_time).delete()
    session = (MercurySession.objects.filter(meter=account_and_contract)
                 .order_by('-created_time').first())
    if session is None:
        return HttpResponse(
            f"Please log in the Contact Energy account that has access to this "
            f"meter: {account_and_contract}. Current logged-in status expires or the "
            f"account doesn't match the meter.",
            status=500)
    try:
        usages = get_data.get_usage(
            session.access_token, session.ocp_key,
            account_and_contract.customer_id,
            account_and_contract.account_id,
            account_and_contract.service_id,
            start_date_midnight, end_date_next_midnight
        )
        for time_slot, value in usages.items():
            new_usage, _ = Usage.objects.update_or_create(
                meter=meter, time_slot=time_slot, value=value)
    except Exception as e:
        return mercury_account(req, failed_reason=f"{type(e).__name__}: {e}")
    else:
        return mercury_account(req, done_signal=True)
