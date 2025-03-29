import pandas as pd
import pyecharts
from bs4 import BeautifulSoup
from django import forms
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
            "applied_date": forms.DateInput({"class": "form-control", "type": "date"}),
            "daily_fixed_price": forms.TextInput(
                {"class": "form-control", "type": "number",
                 "step": 0.01}),
            "GST_ratio": forms.TextInput({"class": "form-control", "type": "number",
                                          "step": 0.001}),
            "levy": forms.TextInput({"class": "form-control", "type": "number",
                                     "step": 0.01}),
            "default_unit_price": forms.TextInput(
                {"class": "form-control", "type": "number",
                 "step": 0.01}),
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
                                           "step": 0.01}),
            "time_from": forms.TimeInput({"class": "form-control", "type": "time",
                                          "step": 1}),
            "time_to": forms.TimeInput({"class": "form-control", "type": "time",
                                        "step": 1}),
        }
        help_texts = {
            "time_from": f"Time zone is {TIME_ZONE}.",
            "time_to": "If ends at midnight or next day, set to 23:59:59 and create "
                       "another special price record. Remember to shift \"days of week\""
                       "one day ahead in the next record.",
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
    return redirect(f'/prices/{price.id}')


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
        initial=Meter.objects.first(),
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
        required=True, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
    )
    end_date = forms.DateField(
        required=True, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
    )


def view_compare(req, failed_reason=None):
    compare_form = Compare()
    return render(req, 'compare.html', context={
        "failed_reason": failed_reason,
        "compare_form": compare_form,
    })


@require_POST
def compare(req):
    compare_form = Compare(req.POST)
    if not compare_form.is_valid():
        return view_compare(req, failed_reason=compare_form.errors.as_text())
    meter = compare_form.cleaned_data['meter']
    start_date = compare_form.cleaned_data['start_date']
    end_date = compare_form.cleaned_data['end_date']
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    start_date_midnight = (pd.to_datetime(start_date)
                           .tz_localize(tz=TIME_ZONE, ambiguous=False))
    end_date_next_midnight = (pd.to_datetime(end_date + pd.Timedelta(days=1))
                              .tz_localize(tz=TIME_ZONE, ambiguous=False))
    usage = Usage.objects.filter(
        meter=meter, time_slot__gte=start_date_midnight,
        time_slot__lt=end_date_next_midnight, value__isnull=False,
    ).order_by('time_slot').values('time_slot', 'value')
    usage = pd.DataFrame.from_records(usage)
    usage['time_slot'] = usage['time_slot'].dt.tz_convert(tz=TIME_ZONE)
    usage['time'] = usage['time_slot'].dt.time
    usage['day_of_week'] = usage['time_slot'].dt.dayofweek

    plan_name = []
    total_price = []
    total_days = (end_date_next_midnight - start_date_midnight) / pd.Timedelta(days=1)
    for i, plan in enumerate(compare_form.cleaned_data['plans']):
        usage[str(plan.id)] = plan.default_unit_price
        for price in plan.price_set.all():
            for j, day in enumerate(Price.DAYS_OF_WEEK):
                if getattr(price, day):
                    usage.loc[(usage['day_of_week'] == j) &
                              (usage['time'] < price.time_to) &
                              (usage['time'] >= price.time_from), str(plan.id)] = (
                        price.unit_price
                    )
        total_price.append(round((
                (usage[str(plan.id)] * (usage['value'] + plan.levy)).sum()
                + total_days * plan.daily_fixed_price
        ) * (1 + plan.GST_ratio)) / 100)
        plan_name.append(("\n\n\n" if i % 2 == 0 else "") +
                         f"{plan.company}\n{plan.name}\n{plan.applied_date}")

    bar = pyecharts.charts.Bar()
    bar.add_xaxis(plan_name)
    bar.add_yaxis("Electricity fee (NZD)", total_price)
    bar.set_global_opts(
        title_opts=pyecharts.options.TitleOpts(
            title="Electricity fee",
        ),
        xaxis_opts=pyecharts.options.AxisOpts(
            type_="category", name="Plan",
            axislabel_opts=pyecharts.options.LabelOpts(interval=0),
        ),
        yaxis_opts=pyecharts.options.AxisOpts(min_=0, name="Electricity fee (NZD)"),
        legend_opts=pyecharts.options.LegendOpts(is_show=False),
    )
    bar_grid = pyecharts.charts.Grid(init_opts=pyecharts.options.InitOpts(width="100%"))
    bar_grid.add(bar, grid_opts=pyecharts.options.GridOpts(pos_bottom="20%"))

    tab = pyecharts.charts.Tab(page_title="New Zealand Electricity")
    tab.add(bar_grid, "Comparison")
    htm = tab.render_embed()

    tree = BeautifulSoup(htm, 'html.parser')
    tab_tag = tree.find('div', class_='tab')
    back_tag = tree.new_tag(
        'a', href='/compare',
        style='font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; '
              'padding: 10px; '
    )
    back_tag.string = 'Back'
    if tab_tag:
        tab_tag.insert_before(back_tag)

    return HttpResponse(str(tree))
