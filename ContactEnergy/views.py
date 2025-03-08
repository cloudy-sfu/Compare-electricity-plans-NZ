import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, date
from random import uniform

import pandas as pd
import pytz
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from requests import Session

from Meter.models import Meter, Usage
from NewZealandElectricity.settings import TIME_ZONE
from .models import *

with open("ContactEnergy/header_login.json") as f:
    header_login = json.load(f)
with open("ContactEnergy/header_csrf_token.json") as f:
    # x-api-key is defined by
    # https://myaccount.contact.co.nz/main.2049c28d6664d8a2ecc3.esm.js
    header_csrf_token = json.load(f)
with open("ContactEnergy/header_usage.json") as f:
    header_usage = json.load(f)
sess = Session()
sess.trust_env = False


class ContactEnergyLogin(forms.Form):
    username = forms.EmailField(
        required=True, widget=forms.EmailInput({'class': 'form-control'})
    )
    password = forms.CharField(
        required=True, widget=forms.PasswordInput({'class': 'form-control'})
    )


def validate_end_date(input_date):
    today = datetime.now(tz=pytz.timezone(TIME_ZONE)).date()
    latest_date = today - timedelta(days=2)
    if input_date > latest_date:
        raise ValidationError("The date cannot be later than " + latest_date.strftime("%Y-%m-%d"))


def validate_start_date(input_date):
    # Contact Energy is founded in 1996-01-01.
    earliest_date = date(1996, 1, 1)
    if input_date < earliest_date:
        raise ValidationError("The date cannot be earlier than " + earliest_date.strftime("%Y-%m-%d"))


class ContactEnergyAccount(forms.Form):
    account_and_contract = forms.ModelChoiceField(
        required=True, widget=forms.Select({"class": "form-select", "style": "white-space: normal;"}),
        queryset=ContactEnergyMeter.objects.all(),
        initial=ContactEnergyMeter.objects.first(),
    )
    start_date = forms.DateField(
        required=True, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        validators=[validate_start_date],
        help_text="No earlier than 1996-01-01."
    )
    end_date = forms.DateField(
        required=True, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        validators=[validate_end_date],
        help_text="No later than the before yesterday."
    )
    overwrite = forms.BooleanField(
        label="",
        required=False,
        widget=forms.CheckboxInput({"style": "width: 1.5rem; height: 1.5rem;"}),
        help_text="Tick this item only when data integrity of this meter has problem. It "
                  "will use fetched data to overwrite existed records."
    )


# Create your views here.
def contact_energy_login(req, failed_reason=None):
    return render(req, 'contact_energy_login.html', {
        "login_form": ContactEnergyLogin(),
        "failed_reason": failed_reason,
    })

@require_POST
def contact_energy_auth(req):
    login_form = ContactEnergyLogin(req.POST)
    if not login_form.is_valid():
        return contact_energy_login(req, failed_reason=login_form.errors.as_text())
    username = login_form.cleaned_data.get('username')
    password = login_form.cleaned_data.get('password')
    # Log in, get authentication (session).
    resp_login = sess.post(
        url="https://api.contact-digital-prod.net/login/v2",
        data=json.dumps({"password": password, "username": username}),
        headers=header_login,
    )
    if resp_login.status_code != 200:
        return contact_energy_login(
            req, failed_reason=f"[{resp_login.status_code}] {resp_login.reason}")
    auth = resp_login.json().get('token')
    if not auth:
        return contact_energy_login(
            req, failed_reason=f"[{resp_login.status_code}] {resp_login.reason}")

    # Get CSRF key and contract ID.
    header_csrf_token["session"] = auth
    resp_csrf_token = sess.get(
        url="https://api.contact-digital-prod.net/accounts/v2?ba=",
        headers=header_csrf_token,
    )
    if resp_csrf_token.status_code != 200:
        return contact_energy_login(
            req, failed_reason=f"[{resp_csrf_token.status_code}] Fail to get CSRF key, "
                               f"account number, and contract number. "
                               f"{resp_csrf_token.reason}"
        )
    resp_csrf_token = resp_csrf_token.json()
    csrf_token = resp_csrf_token.get('xcsrfToken')
    if not csrf_token:
        return contact_energy_login(
            req, failed_reason=f"[{resp_csrf_token.status_code}] Fail to get CSRF key, "
                               f"account number, and contract number. "
                               f"{resp_csrf_token.reason}"
        )
    uuid_ = str(uuid.uuid4())
    for account in resp_csrf_token.get('accountsSummary', []):
        # item exists only when 'id' in keys
        if not account.get('id'):
            continue
        for contract in account.get('contracts', []):
            meter, created = ContactEnergyMeter.objects.get_or_create(
                account_number=account['id'], contract_id=contract['contractId'])
            sess_dbo = ContactEnergySession(
                meter=meter, auth=auth, csrf_token=csrf_token, uuid=uuid_)
            sess_dbo.save()
    return contact_energy_account(req)


def contact_energy_account(req, failed_reason=None):
    return render(req, 'contact_energy_account.html', {
        "account_form": ContactEnergyAccount,
        "failed_reason": failed_reason,
    })


@require_POST
def contact_energy_usage(req):
    account_form = ContactEnergyAccount(req.POST)
    if not account_form.is_valid():
        return HttpResponse(account_form.errors.as_text(), status=500)
    account_and_contract = account_form.cleaned_data.get('account_and_contract')
    start_date = account_form.cleaned_data.get('start_date')
    end_date = account_form.cleaned_data.get('end_date')
    overwrite = account_form.cleaned_data.get('overwrite')
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    meter, created = Meter.objects.get_or_create(
        provider=ContentType.objects.get_for_model(ContactEnergyMeter),
        meter_id=account_and_contract.id,
    )
    if overwrite:
        missing_dates = pd.date_range(start=start_date, end=end_date, freq='1d')
    else:
        missing_dates = get_missing_dates_in_usage(start_date, end_date, meter)
    expiry_time = datetime.now(tz=pytz.timezone(TIME_ZONE)) - timedelta(days=1)
    ContactEnergySession.objects.filter(created_time__lte=expiry_time).delete()
    sess_dbos = (ContactEnergySession.objects.filter(meter=account_and_contract)
                 .order_by('-created_time'))
    if not sess_dbos.exists():
        return HttpResponse(
            f"Please log in the Contact Energy account that has access to this "
            f"meter: {account_and_contract}. Current logged-in status expires or the "
            f"account doesn't match the meter.",
            status=500)
    sess_dbo = sess_dbos[0]
    sess_dbo.total_dates = len(missing_dates)
    sess_dbo.finished_dates = 0
    sess_dbo.failed_dates = 0
    sess_dbo.save()
    contract_id = account_and_contract.contract_id
    account_number = account_and_contract.account_number
    warnings = []
    for date_ in missing_dates:
        url_usage = (f"https://api.contact-digital-prod.net/usage/v2/{contract_id}?"
                     f"ba={account_number}&interval=hourly&from={date_}&to={date_}")
        header_usage_ins = header_usage.copy()
        header_usage_ins['Authorization'] = sess_dbo.auth
        header_usage_ins['X-Correlation-Id'] = sess_dbo.uuid
        header_usage_ins['X-Csrf-Token'] = sess_dbo.csrf_token
        response = sess.post(url=url_usage, headers=header_usage_ins)
        time.sleep(round(uniform(0.7, 1.3), 2))
        if response.status_code != 200:
            return HttpResponse(f"Fail to get usage. Status code: {response.status_code}. "
                                f"Reason: {response.reason}", status=500)
        usage = response.json()
        if len(usage) == 0:
            warnings.append(f"The usage on {date_} is empty.")
            sess_dbo.failed_dates = sess_dbo.failed_dates + 1
            sess_dbo.save()
            continue
        try:
            with transaction.atomic():
                existed_usages = Usage.objects.filter(
                    meter=meter, time_slot__day=date_.day,
                    time_slot__month=date_.month, time_slot__year=date_.year,
                )
                existed_usages.delete()
                for row in usage:
                    date_time_ = pd.to_datetime(row['date'])
                    try:
                        amount = float(row['value'])
                    except ValueError:
                        warnings.append(f"Amount is not a number on {date_time_}.")
                        amount = None
                    new_usage = Usage(meter=meter, time_slot=date_time_, value=amount)
                    new_usage.save()
                sess_dbo.finished_dates = sess_dbo.finished_dates + 1
                sess_dbo.save()
        except json.decoder.JSONDecodeError:
            warnings.append(f"Fail to parse usage on {date_} from Contact Energy.")
            sess_dbo.failed_dates = sess_dbo.failed_dates + 1
            sess_dbo.save()
            continue
    if warnings:
        return HttpResponse(' '.join(warnings), status=500)
    else:
        return HttpResponse()


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
def contact_energy_progress(req):
    account_form = ContactEnergyAccount(req.POST)
    if not account_form.is_valid():
        raise Exception(account_form.errors.as_text())  # trigger 500 error
    account_and_contract = account_form.cleaned_data.get('account_and_contract')
    sess_dbos = (ContactEnergySession.objects.filter(meter=account_and_contract)
                 .order_by('-created_time'))
    if not sess_dbos.exists():
        raise Exception("Session with Contact Energy is not created.")
    sess_dbo = sess_dbos[0]
    if sess_dbo.total_dates == 0:
        return JsonResponse({"success": 100, "failed": 0, "unhandled": 0})
    else:
        progress_success = round(sess_dbo.finished_dates / sess_dbo.total_dates * 100)
        progress_failed = round(sess_dbo.failed_dates / sess_dbo.total_dates * 100)
        progress_unhandled = 100 - progress_success - progress_failed
        return JsonResponse({"success": progress_success, "failed": progress_failed,
                             "unhandled": progress_unhandled})


class AbstractMeterForm(forms.Form):
    database = forms.FileField(
        required=True, widget=forms.FileInput({"class": "form-control"}),
        help_text="\"contact_energy.db\" file from the previous version of this program."
    )


def view_import_from_v1(req):
    return render(req, "contact_energy_import.html", context={
        "abstract_meter_form": AbstractMeterForm(),
        "time_zone": TIME_ZONE,
    })


@require_POST
def import_from_v1(req):
    meter_form = AbstractMeterForm(req.POST, req.FILES)
    if not meter_form.is_valid():
        return HttpResponse(meter_form.errors.as_text(), status=500)
    db = meter_form.cleaned_data['database']
    fp = default_storage.save(
        "ContactEnergy/contact_energy.db", ContentFile(db.read()))
    try:
        c = sqlite3.connect(fp)
        meters = pd.read_sql_query("select ROWID, * from meter", c)
        usage = pd.read_sql_query("select * from usage", c)
        c.close()
        os.remove(fp)
        meters_id_map = {}
        for _, row in meters.iterrows():
            meter, created = ContactEnergyMeter.objects.get_or_create(
                account_number=f'OLD{row['account_number']}',
                contract_id=row['contract_id']
            )
            g_meter, created = Meter.objects.get_or_create(
                provider=ContentType.objects.get_for_model(ContactEnergyMeter),
                meter_id=meter.id,
            )
            meters_id_map[row['rowid']] = g_meter.id
        usage['meter_id'] = usage['meter_id'].apply(meters_id_map.get)
        usage['time_slot'] = (pd.to_datetime(usage[['year', 'month', 'day', 'hour']]).dt
                              .tz_localize(TIME_ZONE, ambiguous='infer'))
        for meter_id, subset in usage.groupby('meter_id'):
            try:
                g_meter = Meter.objects.get(id=meter_id)
            except Meter.DoesNotExist:
                continue
            for _, row in subset.iterrows():
                usage = Usage(meter=g_meter, time_slot=row['time_slot'], value=row['value'])
                usage.save()
    except Exception as e:
        return HttpResponse(str(e), status=500)
    return HttpResponse()
