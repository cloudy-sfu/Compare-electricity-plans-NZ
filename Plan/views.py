from functools import partial

import numpy as np
import pandas as pd
from django import forms
from django.db.models import Min, Max
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from Meter.models import Meter, Usage
from NewZealandElectricity.settings import TIME_ZONE
from .models import ChargingPlan, Price


# Create your views here.
def view_plans(req, failed_reason=None):
    plans = ChargingPlan.objects.all()
    return render(req, "plans.html", context={
        "plans": plans, "failed_reason": failed_reason,
    })


class ChangeChargingPlan(forms.ModelForm):
    class Meta:
        model = ChargingPlan
        exclude = []
        widgets = {
            "company": forms.TextInput({"class": "form-control"}),
            "name": forms.TextInput({"class": "form-control"}),
            "daily_fixed_price": forms.TextInput(
                {"class": "form-control", "type": "number",
                 "step": "any"}),
            "GST_ratio": forms.TextInput({"class": "form-control", "type": "number",
                                          "step": "any"}),
            "levy": forms.TextInput({"class": "form-control", "type": "number",
                                     "step": "any"}),
            "default_unit_price": forms.TextInput(
                {"class": "form-control", "type": "number",
                 "step": "any"}),
        }
        labels = {
            "daily_fixed_price": "Fixed daily charge",
            "default_unit_price": "Unit price in other time",
        }


def view_change_plan(req, plan_id: int, failed_reason=None):
    try:
        plan = ChargingPlan.objects.get(id=plan_id)
    except ChargingPlan.DoesNotExist:
        return view_plans(req, "This charging plan is not found.")
    return render(req, 'change_plan.html', context={
        "change_plan_form": ChangeChargingPlan(instance=plan),
        "plan": plan,
        "failed_reason": failed_reason,
    })


@require_POST
def change_plan(req, plan_id: int):
    try:
        plan = ChargingPlan.objects.get(id=plan_id)
    except ChargingPlan.DoesNotExist:
        return add_plan(req)
    plan_form = ChangeChargingPlan(req.POST, instance=plan)
    if not plan_form.is_valid():
        return render(req, 'change_plan.html', context={
            "change_plan_form": ChangeChargingPlan(req.POST),
            "failed_reason": "The form is not valid.",
        })
    plan_form.save()
    return redirect(f"/plans/{plan.id}")


def view_add_plan(req, failed_reason=None):
    return render(req, 'change_plan.html', context={
        "change_plan_form": ChangeChargingPlan(),
        "failed_reason": failed_reason,
    })


@require_POST
def add_plan(req):
    plan = ChargingPlan()
    plan_form = ChangeChargingPlan(req.POST, instance=plan)
    if not plan_form.is_valid():
        return render(req, 'change_plan.html', context={
            "change_plan_form": ChangeChargingPlan(req.POST),
            "failed_reason": "The form is not valid.",
        })
    plan_form.save()
    return redirect(f"/plans/{plan.id}")


def delete_plan(req, plan_id: int):
    try:
        plan = ChargingPlan.objects.get(id=plan_id)
        plan.delete()
    except ChargingPlan.DoesNotExist:
        pass
    return redirect("/plans")


class ChangePrice(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=[(d, d) for d in Price.DAYS_OF_WEEK],
        widget=forms.SelectMultiple({'style': 'display: block; width: 100%;',
                                     'size': '7', 'class': 'form-control'}),
        required=True,
        help_text="Hold \"Control\" and click to select multiple items."
    )

    class Meta:
        model = Price
        fields = ['plan', 'name', 'unit_price', 'time_from', 'time_to']
        widgets = {
            'plan': forms.HiddenInput(),
            "name": forms.TextInput({"class": "form-control"}),
            "unit_price": forms.TextInput({"class": "form-control", "type": "number",
                                           "step": "any"}),
            "time_from": forms.TimeInput({"class": "form-control", "type": "time",
                                          "step": 1}),
            "time_to": forms.TimeInput({"class": "form-control", "type": "time",
                                        "step": 1}),
        }
        help_texts = {
            "time_from": f"Time zone is {TIME_ZONE}.",
            "time_to": "If end time is smaller than start time, it means the next day.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial_days = []
        if self.instance:
            for day in Price.DAYS_OF_WEEK:
                if getattr(self.instance, day, False):
                    initial_days.append(day)
        self.fields['days_of_week'].initial = initial_days

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected_days = self.cleaned_data.get('days_of_week', [])
        for day in Price.DAYS_OF_WEEK:
            setattr(instance, day, day in selected_days)
        if commit:
            instance.save()
        return instance


def view_change_price(req, price_id: int, failed_reason=None):
    try:
        price = Price.objects.get(id=price_id)
    except Price.DoesNotExist:
        return view_plans(req, "This special price record is not found.")
    return render(req, 'change_price.html', context={
        "plan": price.plan,
        "change_price_form": ChangePrice(instance=price),
        "price": price,
        "failed_reason": failed_reason,
    })


@require_POST
def change_price(req, price_id: int):
    try:
        price = Price.objects.get(id=price_id)
    except Price.DoesNotExist:
        return add_price(req)
    price_form = ChangePrice(req.POST, instance=price)
    if not price_form.is_valid():
        return render(req, 'change_price.html', context={
            "plan": price.plan,
            "change_price_form": ChangePrice(instance=price),
            "price": price,
            "failed_reason": price_form.errors.as_text(),
        })
    price_form.save()
    return redirect(f'/plans/{price.plan.id}')


@require_POST
def add_price(req):
    price = Price()
    price_form = ChangePrice(req.POST, instance=price)
    if not price_form.is_valid():
        try:
            plan_id = int(req.POST.get('plan'))
        except ValueError:
            return view_plans(req, "This special price record is not found.")
        try:
            plan = ChargingPlan.objects.get(id=plan_id)
        except ChargingPlan.DoesNotExist:
            return view_plans(req, "This special price record is not found.")
        return render(req, 'change_price.html', context={
            "plan": plan,
            "change_price_form": price_form,
            "price": None,
            "failed_reason": price_form.is_valid(),
        })
    price_form.save()
    return redirect(f'/prices/{price.id}')


def view_add_price(req, plan_id: int, failed_reason=None):
    try:
        plan = ChargingPlan.objects.get(id=plan_id)
    except ChargingPlan.DoesNotExist:
        return view_plans(req, "This charging plan is not found.")
    return render(req, 'change_price.html', context={
        "plan": plan,
        "change_price_form": ChangePrice(initial={"plan": plan}),
        "failed_reason": failed_reason,
    })


def delete_price(req, price_id: int):
    try:
        price = Price.objects.get(id=price_id)
        plan = price.plan
        price.delete()
        return redirect(f'/plans/{plan.id}')
    except Price.DoesNotExist:
        return redirect("/plans")


class Compare(forms.Form):
    meter = forms.ModelChoiceField(
        queryset=Meter.objects.all(), required=True,
        widget=forms.Select({"class": "form-select"}),
    )
    plans = forms.ModelMultipleChoiceField(
        queryset=ChargingPlan.objects.all(),
        widget=forms.SelectMultiple({'style': 'display: block; width: 100%;',
                                     'size': '7', 'class': 'form-control'}),
        required=True,
        help_text="Hold \"Control\" and click to select multiple items."
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        help_text="Optional: the earliest record in database by default. If the earliest "
                  "record is more than 1 year before the latest record, the start date "
                  "is 1 year before the end date."
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        help_text="Optional: the latest record in database by default."
    )

    def __init__(self, *args, **kwargs):
        super(Compare, self).__init__(*args, **kwargs)
        try:
            self.fields['meter'].initial = Meter.objects.first()
        except (OperationalError, ProgrammingError):
            pass


def view_compare(req, failed_reason=None):
    compare_form = Compare()
    return render(req, 'compare.html', context={
        "failed_reason": failed_reason,
        "compare_form": compare_form,
    })


def overlap(a0, a1, b0, b1): # intersection length, >= 0
    lo, hi = max(a0, b0), min(a1, b1)
    return max(hi - lo, pd.Timedelta(0))


def windows(s, start, end):
    # yield concrete [w0, w1) intervals for special `s` that could touch [start,end)
    # scan each calendar date the slot may reference (prev day covers overnight tail)
    for day in pd.date_range((start - pd.Timedelta(days=1)).normalize(),
                              end.normalize(), freq="D", tz=start.tz):
        if not getattr(s, Price.DAYS_OF_WEEK[day.dayofweek]):
            continue
        w0 = day + pd.Timedelta(hours=s.time_from.hour, minutes=s.time_from.minute)
        if s.time_from < s.time_to:                       # same-day window
            w1 = day + pd.Timedelta(hours=s.time_to.hour, minutes=s.time_to.minute)
        else:                                             # overnight -> ends next day
            w1 = day + pd.Timedelta(days=1,
                    hours=s.time_to.hour, minutes=s.time_to.minute)
        yield w0, w1


def record_cost(row, prices, plan):
    start = row["time_slot"]
    end = row["time_slot_end"]
    slot_sec = (end - start).total_seconds()
    remaining = end - start
    weighted = 0.0
    for s in prices:  # earlier specials take priority
        covered = pd.Timedelta(0)
        for w0, w1 in windows(s, start, end):
            covered += overlap(start, end, w0, w1)
        covered = min(covered, remaining)
        weighted += covered.total_seconds() * s.unit_price
        remaining -= covered
    weighted += remaining.total_seconds() * plan.default_unit_price
    eff = weighted / slot_sec + plan.levy
    return row["value"] * eff


@require_POST
def compare(req):
    compare_form = Compare(req.POST)
    if not compare_form.is_valid():
        return view_compare(req, failed_reason=compare_form.errors.as_text())
    meter = compare_form.cleaned_data['meter']
    start_date = compare_form.cleaned_data['start_date']
    end_date = compare_form.cleaned_data['end_date']
    if start_date and end_date:
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        start_date_midnight = (pd.to_datetime(start_date)
                               .tz_localize(tz=TIME_ZONE, ambiguous=False))
        end_date_next_midnight = (pd.to_datetime(end_date + pd.Timedelta(days=1))
                                  .tz_localize(tz=TIME_ZONE, ambiguous=False))
    else:
        usage_scope = Usage.objects.filter(meter=meter, value__isnull=False)
        if usage_scope.count() == 0:
            return HttpResponse(f"Meter {meter} has no record.", status=500)
        usage_stats = usage_scope.aggregate(
            start_date=Min('time_slot'),
            end_date=Max('time_slot'),
        )
        start_date_midnight = pd.to_datetime(usage_stats['start_date'])
        end_date_next_midnight = pd.to_datetime(
            usage_stats['end_date'] + pd.Timedelta(days=1))
        start_date_midnight = max(
            start_date_midnight, end_date_next_midnight - pd.Timedelta(days=366))
    usage = Usage.objects.filter(
        meter=meter, time_slot__gte=start_date_midnight,
        time_slot__lt=end_date_next_midnight, value__isnull=False,
    ).order_by('time_slot').values('time_slot', 'value')
    usage = pd.DataFrame.from_records(usage)
    if usage.shape[0] == 0:
        return render(req, "compare.html", {
            "failed_reason": "No electricity usage.",
            "compare_form": compare_form
        })
    usage['time_slot'] = usage['time_slot'].dt.tz_convert(tz=TIME_ZONE)

    if usage.shape[0] > 2:
        last_2_idx = usage.index[-2]
        last_1_idx = usage.index[-1]
        usage['time_slot_end'] = usage['time_slot'].shift(-1)
        usage.loc[last_1_idx, 'time_slot_end'] = usage.loc[last_1_idx, 'time_slot'] + \
            (usage.loc[last_2_idx, 'time_slot_end'] - usage.loc[last_2_idx, 'time_slot'])
    elif usage.shape[0] == 2:
        usage['time_slot_end'] = usage['time_slot'] + \
            (usage.loc[1, 'time_slot'] - usage.loc[0, 'time_slot'])
    elif usage.shape[0] == 1:
        usage['time_slot_end'] = usage['time_slot'] + pd.Timedelta(hours=1)
    else:
        plans = [
            {
                "Company": plan.company,
                "Plan name": plan.name,
                "Total fee": 0,
            }
            for plan in compare_form.cleaned_data['plans']
        ]
        plans = pd.DataFrame(plans)
        plans.sort_values(inplace=True, by="Total fee")
        plans_html = plans.to_html(classes='table mt-4 table-bordered', index=False)
        return render(req, "compare_results.html", {"plans": plans_html})

    total_days = (end_date_next_midnight - start_date_midnight) / pd.Timedelta(days=1)
    plans = []
    for plan in compare_form.cleaned_data['plans']:
        record_cost_per = partial(record_cost, prices=plan.price_set.all(), plan=plan)
        variable_fee = usage.apply(record_cost_per, axis=1).sum()
        fixed_fee = total_days * plan.daily_fixed_price
        plans.append({
            "Company": plan.company,
            "Plan name": plan.name,
            "Total fee": round(
                (variable_fee + fixed_fee) * (1 + plan.GST_ratio)
                , 2
            ),
        })
    plans = pd.DataFrame(plans)
    plans.sort_values(inplace=True, by="Total fee")
    plans_html = plans.to_html(classes='table mt-4 table-bordered', index=False)

    return render(req, "compare_results.html", {"plans": plans_html})
