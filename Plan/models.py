from django.db import models


# Create your models here.
class ChargingPlan(models.Model):
    company = models.CharField(max_length=32)
    name = models.CharField(max_length=64)
    applied_date = models.DateField()
    daily_fixed_price = models.FloatField(help_text="Exclude GST. Unit: New Zealand cent")
    GST_ratio = models.FloatField(default=0.15)
    levy = models.FloatField(help_text="Exclude GST. Unit: New Zealand cent")
    default_unit_price = models.FloatField(
        help_text="The unit price in other time. It excludes the time when special prices "
                  "are applied. Exclude GST.  Unit: New Zealand cent"
    )

    def __str__(self):
        return f"{self.company} {self.name} {self.applied_date.strftime('%Y-%m-%d')}"


class Price(models.Model):
    plan = models.ForeignKey(ChargingPlan, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=32,
        help_text="Time period name that this price applies on, e.g. peak, off-peak, "
                  "daytime, night, weekdays, weekend."
    )
    unit_price = models.FloatField(help_text="Exclude GST. Unit: New Zealand cent")
    DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
                    'Sunday']
    for day in DAYS_OF_WEEK:
        locals()[day] = models.BooleanField(default=False)
    time_from = models.TimeField(help_text="In format of HH:MM:SS.")
    time_to = models.TimeField(
        help_text="In format of HH:MM:SS. "
                  "If ends at midnight, input 23:59:59. If lasts to next day, create "
                  "another record that time_from = 00:00:00 (remember days of week +1)."
    )

    def day_of_week_full_name(self):
        days = []
        for day in self.DAYS_OF_WEEK:
            if self.__dict__[day]:
                days.append(day)
        return ", ".join(days)

    def day_of_week_short_name(self):
        days = []
        for day in self.DAYS_OF_WEEK:
            if self.__dict__[day]:
                days.append(day[:3])
        return ", ".join(days)

    def day_of_week_iso(self):
        """
        https://docs.python.org/3/library/datetime.html#datetime.date.isoweekday
        Monday = 1, Sunday = 7
        :return:
        """
        days = []
        for i, day in enumerate(self.DAYS_OF_WEEK):
            if self.__dict__[day]:
                days.append(str(i+1))
        return ", ".join(days)
