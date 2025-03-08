from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


# Create your models here.
class Meter(models.Model):
    provider = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    meter_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('provider', 'meter_id')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['provider', 'meter_id'], name='unique_meter'),
        ]

    def __str__(self):
        return f"{self.provider.app_label}, {self.content_object}"


class Usage(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE)
    time_slot = models.DateTimeField()
    value = models.FloatField(verbose_name="Electricity usage amount (kWh)", null=True)

    def __str__(self):
        return f"{self.meter} {self.time_slot.strftime('%Y-%m-%d %H:%M')}"
