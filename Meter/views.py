import numpy as np
import pandas as pd
import pyecharts
from bs4 import BeautifulSoup
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, OperationalError, ProgrammingError
from django.db.models import Q, Min, Max
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from NewZealandElectricity.settings import TIME_ZONE
from .admin import get_meter_types
from .models import Meter, Usage

# Set the locale to English to bypass browser language detection issues (e.g., en-NZ)
pyecharts.globals.CurrentConfig.LOCALE = pyecharts.globals.Locale.EN

# Create your views here.
def main(req):
    data_source = [
        {"display_name": "Contact Energy", "entry": "/get_data_contact"},
        {"display_name": "Mercury", "entry": "/get_data_mercury"},
    ]
    return render(req, "index.html", context={
        "data_source": data_source,
    })


class MeterForm(forms.Form):
    previous_data_source = forms.ChoiceField(
        required=True,
        widget=forms.Select({"class": "form-select", "style": "white-space: normal;"}),
    )
    new_data_source = forms.ChoiceField(
        required=True,
        widget=forms.Select({"class": "form-select", "style": "white-space: normal;"}),
    )
    on_overlapped = forms.ChoiceField(
        required=True, choices=[('prev', "Keep previous"), ('new', "Keep new")],
        widget=forms.Select({"class": "form-select", "style": "white-space: normal;"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter ContentType to only include specific models
        allowed_content_types = ContentType.objects.filter(
            Q(app_label='ContactEnergy', model__in=['contactenergymeter'])
        )
        meters = Meter.objects.filter(provider__in=allowed_content_types)
        choices = [
            (f"{meter.provider_id};{meter.meter_id}",
             f"{meter.provider.app_label}, {meter.content_object}")
            for meter in meters
        ]
        self.fields['previous_data_source'].choices = choices
        self.fields['new_data_source'].choices = choices


def view_migrate_meters(req, failed_reason=None):
    meter_form = MeterForm()
    return render(req, "meters_list.html", context={
        "meter_form": meter_form,
        "failed_reason": failed_reason,
    })


@require_POST
def migrate_meters(req):
    meter_form = MeterForm(req.POST)
    if not meter_form.is_valid():
        return HttpResponse(meter_form.errors.as_text(), status=500)
    prev_ct, prev_meter_id = meter_form.cleaned_data['previous_data_source'].split(';')
    new_ct, new_meter_id = meter_form.cleaned_data['new_data_source'].split(';')
    try:
        prev_ct = int(prev_ct)
        prev_meter_id = int(prev_meter_id)
        new_ct = int(new_ct)
        new_meter_id = int(new_meter_id)
    except ValueError:
        return HttpResponse("Submission's format is invalid.", status=500)
    if prev_ct == new_ct and prev_meter_id == new_meter_id:
        return HttpResponse()
    new_providers = get_meter_types().filter(id=new_ct)
    if not new_providers.exists():
        return HttpResponse("New electricity provider does not exist.", status=500)
    new_provider = new_providers[0].model_class()
    new_meter = new_provider.objects.filter(id=new_meter_id)
    if not new_meter.exists():
        return HttpResponse("new meter does not exist. Please retrieve data from the new "
                            "electricity provider at least once.", status=500)
    prev_meter_g, created = Meter.objects.get_or_create(
        provider_id=prev_ct, meter_id=prev_meter_id)
    try:
        with transaction.atomic():
            new_meter_g = Meter.objects.get(provider_id=new_ct, meter_id=new_meter_id)
            new_usage = Usage.objects.filter(meter=new_meter_g)
            new_usage_range = new_usage.aggregate(
                min_time=Min("time_slot"),
                max_time=Max("time_slot")
            )
            existed_usages = Usage.objects.filter(meter=prev_meter_g)
            existed_usages_range = existed_usages.aggregate(
                min_time=Min("time_slot"),
                max_time=Max("time_slot")
            )
            if meter_form.cleaned_data['on_overlapped'] == 'prev':
                new_usage.filter(
                    time_slot__gte=existed_usages_range['min_time'],
                    time_slot__lte=existed_usages_range['max_time'],
                ).delete()
            else:  # on_overlapped = new
                existed_usages.filter(
                    time_slot__gte=new_usage_range['min_time'],
                    time_slot__lte=new_usage_range['max_time'],
                ).delete()
            for usage in new_usage:
                usage.meter = prev_meter_g
                usage.save()
            new_meter_g.delete()
    except Meter.DoesNotExist:
        pass
    except OperationalError:
        HttpResponse("Database busy, please try later.", status=500)
    prev_meter_g.provider_id = new_ct
    prev_meter_g.meter_id = new_meter_id
    prev_meter_g.save()
    prev_providers = get_meter_types().filter(id=prev_ct)
    if prev_providers.exists():
        prev_provider = prev_providers[0].model_class()
        prev_meter = prev_provider.objects.filter(id=prev_meter_id)
        if prev_meter.exists():
            prev_meter.delete()
    return HttpResponse()


class CheckIntegrity(forms.Form):
    meter = forms.ModelChoiceField(
        required=True, queryset=Meter.objects.all(),
        widget=forms.Select({"class": "form-select", "style": "white-space: normal;"})
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        help_text="Optional: the earliest record in database by default."
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput({
            "class": "form-control", "type": "date", "min": "1996-01-01"}),
        help_text="Optional: the latest record in database by default."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['meter'].initial = Meter.objects.first()
        except (OperationalError, ProgrammingError):
            pass

def view_integrity(req, failed_reason=None):
    return render(req, "integrity.html", context={
        "check_integrity_form": CheckIntegrity(),
        "failed_reason": failed_reason,
    })

@require_POST
def check_integrity(req):
    ci = CheckIntegrity(req.POST)
    if not ci.is_valid():
        return view_integrity(req, failed_reason=ci.errors.as_text())
    meter = ci.cleaned_data['meter']
    start_date = ci.cleaned_data['start_date']
    end_date = ci.cleaned_data['end_date']
    if start_date and end_date:
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        start_date_midnight = (pd.to_datetime(start_date)
                               .tz_localize(tz=TIME_ZONE, ambiguous=False))
        end_date_next_midnight = (pd.to_datetime(end_date + pd.Timedelta(days=1))
                                  .tz_localize(tz=TIME_ZONE, ambiguous=False))
        usage = Usage.objects.filter(
            meter=meter, time_slot__gte=start_date_midnight,
            time_slot__lt=end_date_next_midnight, value__isnull=False,
        ).order_by('time_slot').values('time_slot')
    else:
        usage_scope = Usage.objects.filter(meter=meter, value__isnull=False)
        if usage_scope.count() == 0:
            return HttpResponse(f"Meter {meter} has no record.", status=500)
        usage = usage_scope.order_by('time_slot').values('time_slot')
    usage = pd.DataFrame.from_records(usage)
    if usage.shape[0] < 2:
        return render(req, 'integrity_results.html', context={
            "meter": str(meter),
            "start_date": start_date,
            "end_date": end_date,
            "segments": [],
        })
    usage['time_slot'] = usage['time_slot'].dt.tz_convert(tz=TIME_ZONE)
    
    diff_b = usage['time_slot'].diff()
    diff_f = usage['time_slot'].shift(-1) - usage['time_slot']
    interval = pd.concat([diff_b, diff_f], axis=1).min(axis=1)
    
    if interval.isna().all():
        interval = interval.fillna(pd.Timedelta(hours=1))
        
    freq_counts = interval.value_counts()
    valid_freqs = freq_counts[freq_counts > max(2, len(interval) * 0.01)].index
    if valid_freqs.empty:
        valid_freqs = pd.Index([interval.mode()[0]])
        
    smoothed_interval = interval.where(interval.isin(valid_freqs)).ffill().bfill()
    usage['segment_id'] = (smoothed_interval != smoothed_interval.shift()).cumsum()
    
    segments_context = []
    for seg_id, group in usage.groupby('segment_id'):
        min_time = group['time_slot'].iloc[0]
        max_time = group['time_slot'].iloc[-1]
        freq = smoothed_interval.loc[group.index[0]]
        
        full_index = pd.date_range(min_time, max_time, freq=freq)
        missing_time = full_index.difference(group['time_slot'])

        if missing_time.shape[0] == 0:
            missing_time_pairs = pd.DataFrame(columns=['Start time', 'End time'])
        else:
            common_mask = missing_time.to_series().diff() > freq
            common_idx = np.argwhere(common_mask.values).flatten()
            start_idx = [0] + common_idx.tolist()
            missing_start_time = missing_time[start_idx]
            end_idx = (common_idx - 1).tolist() + [missing_time.shape[0] - 1]
            missing_end_time = missing_time[end_idx]
            missing_time_pairs = pd.DataFrame({
                "Start time": missing_start_time,
                "End time": missing_end_time,
            })

        theoretical_total = round((max_time - min_time) / freq) + 1
        
        segments_context.append({
            "min_time": min_time,
            "max_time": max_time,
            "n_missing": missing_time.shape[0],
            "n_total": group.shape[0],
            "theoretical_total": theoretical_total,
            "missing_time": missing_time_pairs.to_html(
                classes='table table-striped table-bordered', index=False),
            "sampling_frequency": freq,
        })

    return render(req, 'integrity_results.html', context={
        "meter": str(meter),
        "start_date": start_date,
        "end_date": end_date,
        "segments": segments_context,
    })


class SelectMeter(forms.Form):
    meter = forms.ModelChoiceField(
        queryset=Meter.objects.all(), required=True,
        widget=forms.Select({"class": "form-select"}),
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
        super().__init__(*args, **kwargs)
        try:
            self.fields['meter'].initial = Meter.objects.first()
        except (OperationalError, ProgrammingError):
            pass


def view_select_meter(req, failed_reason=None):
    select_meter_form = SelectMeter()
    return render(req, 'select_meter.html', context={
        "select_meter_form": select_meter_form,
        "failed_reason": failed_reason,
    })


def count_weeks(start_date, end_date) -> int:
    """
    Calculate the number of weeks from start_date to end_date,
    considering incomplete weeks as full weeks. Weeks start on Sunday.

    Args:
    start_date (str): Start date in format of datetime.date
    end_date (str): End date in format of datetime.date

    Returns:
    int: Number of weeks.
    """
    start_week_sunday = start_date - pd.Timedelta(days=(start_date.weekday() + 1) % 7)
    end_week_saturday = end_date + pd.Timedelta(days=(5 - end_date.weekday()) % 7)
    total_days = (end_week_saturday - start_week_sunday).days + 1
    total_weeks = round(total_days / 7)
    return total_weeks


@require_POST
def select_meter(req):
    select_meter_form = SelectMeter(req.POST)
    if not select_meter_form.is_valid():
        return view_select_meter(req, select_meter_form.errors.as_text())
    meter = select_meter_form.cleaned_data['meter']
    start_date = select_meter_form.cleaned_data['start_date']
    end_date = select_meter_form.cleaned_data['end_date']
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
        if start_date_midnight.tzinfo is not None:
            start_date_midnight = start_date_midnight.tz_convert(TIME_ZONE)
        else:
            start_date_midnight = start_date_midnight.tz_localize(TIME_ZONE)
        start_date_midnight = start_date_midnight.normalize()

        end_date_next_midnight = pd.to_datetime(usage_stats['end_date'])
        if end_date_next_midnight.tzinfo is not None:
            end_date_next_midnight = end_date_next_midnight.tz_convert(TIME_ZONE)
        else:
            end_date_next_midnight = end_date_next_midnight.tz_localize(TIME_ZONE)
        end_date_next_midnight = end_date_next_midnight.normalize() + pd.Timedelta(days=1)
        
        start_date_midnight = max(
            start_date_midnight, end_date_next_midnight - pd.Timedelta(days=366))
        start_date = start_date_midnight.date()
        end_date = end_date_next_midnight.date()
    usage = Usage.objects.filter(
        meter=meter, time_slot__gte=start_date_midnight,
        time_slot__lt=end_date_next_midnight, value__isnull=False,
    ).order_by('time_slot').values('time_slot', 'value')
    usage = pd.DataFrame.from_records(usage)
    if usage.shape[0] == 0:
        return view_select_meter(req, failed_reason="No electricity usage.")
    usage['time_slot'] = usage['time_slot'].dt.tz_convert(tz=TIME_ZONE)
    line = pyecharts.charts.Line(init_opts=pyecharts.options.InitOpts(width="100%"))
    line.add_xaxis(usage['time_slot'].dt.strftime("%Y-%m-%d %H:%M").tolist())
    line.add_yaxis(
        "Electricity (kWh)", usage['value'].tolist(),
        sampling='lttb', is_smooth=True,
        label_opts=pyecharts.options.LabelOpts(is_show=False)
    )
    line.set_global_opts(
        title_opts=pyecharts.options.TitleOpts(
            title="Line plot of electricity usage",
        ),
        datazoom_opts=[
            pyecharts.options.DataZoomOpts(xaxis_index=0),
        ],
        yaxis_opts=pyecharts.options.AxisOpts(min_=0, name="Electricity (kWh)"),
        legend_opts=pyecharts.options.LegendOpts(is_show=False),
    )
    usage['date'] = usage['time_slot'].dt.strftime("%Y-%m-%d")
    usage_daily = usage.groupby('date').aggregate('sum', 'value')
    usage_daily.reset_index(inplace=True)
    usage_daily['value'] = usage_daily['value'].round(2)
    tooltip_formatter = pyecharts.commons.utils.JsCode("""function(params){
    const date = params.value[0];
    const value = params.value[1];
    return date + '<br>' + value + ' kWh';
}""")

    heatmap = pyecharts.charts.Calendar(
        init_opts=pyecharts.options.InitOpts(width="100%"),
    )
    heatmap.add(
        series_name="Electricity (kWh)",
        yaxis_data=usage_daily.to_dict(orient='split', index=False)['data'],
        calendar_opts=pyecharts.options.CalendarOpts(
            range_=[start_date, end_date],
            width=str(20 * count_weeks(start_date, end_date)),
            height='140',
        ),
        tooltip_opts=pyecharts.options.TooltipOpts(
            formatter=tooltip_formatter
        )
    )
    heatmap.set_global_opts(
        title_opts=pyecharts.options.TitleOpts(
            title="Total electricity usage in each day",
        ),
        visualmap_opts=pyecharts.options.VisualMapOpts(
            min_=0, max_=usage_daily['value'].max(),
            orient="horizontal",
            is_piecewise=True,
            pos_top="230px",
            pos_left="100px",
        ),
        legend_opts=pyecharts.options.LegendOpts(is_show=False),
    )

    usage['hour'] = usage['time_slot'].dt.hour
    usage_hours = usage.groupby('hour').aggregate('mean', 'value')
    usage_hours['value'] = usage_hours['value'].round(2)
    bar = pyecharts.charts.Bar(init_opts=pyecharts.options.InitOpts(width="100%"))
    bar.add_xaxis(usage_hours.index.tolist())
    bar.add_yaxis("Electricity (kWh)", usage_hours['value'].tolist())
    bar.set_global_opts(
        title_opts=pyecharts.options.TitleOpts(
            title="Average electricity usage in the same hour of every day",
        ),
        xaxis_opts=pyecharts.options.AxisOpts(type_="category", name="Hour"),
        yaxis_opts=pyecharts.options.AxisOpts(min_=0, name="Electricity (kWh)"),
        legend_opts=pyecharts.options.LegendOpts(is_show=False),
    )

    total_usage = usage['value'].sum()
    total = pyecharts.charts.Bar()
    total.add_xaxis(['Total'])
    total.add_yaxis("Electricity (kWh)", [total_usage])
    total.set_global_opts(
        title_opts=pyecharts.options.TitleOpts(
            title=f"Total electricity usage from {start_date} to {end_date}",
        ),
        xaxis_opts=pyecharts.options.AxisOpts(type_="category"),
        yaxis_opts=pyecharts.options.AxisOpts(min_=0, name="Electricity (kWh)"),
        legend_opts=pyecharts.options.LegendOpts(is_show=False),
    )

    tab = pyecharts.charts.Tab(page_title="New Zealand Electricity")
    tab.add(total, "Total view")
    tab.add(bar, "Circadian view")
    tab.add(heatmap, "Calendar view")
    tab.add(line, "Time series view")
    htm = tab.render_embed()

    tree = BeautifulSoup(htm, 'html.parser')
    tab_tag = tree.find('div', class_='tab')
    back_tag = tree.new_tag(
        'a', href='/meters',
        style='font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; '
              'padding: 10px; '
    )
    back_tag.string = 'Back'
    if tab_tag:
        tab_tag.insert_before(back_tag)

    return HttpResponse(str(tree))
