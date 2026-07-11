from django.db import models

# Create your models here.
class MercuryMeter(models.Model):
    customer_id = models.CharField(max_length=32)
    account_id = models.CharField(max_length=32)
    service_id = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    address = models.TextField(max_length=500)
    service_start_time = models.DateField()

    def __str__(self):
        return f"{self.name} ({self.address}), Service {self.service_id}"

class MercurySession(models.Model):
    meter = models.ForeignKey(MercuryMeter, on_delete=models.CASCADE)
    access_token = models.TextField()
    ocp_key = models.CharField(max_length=32)
    created_time = models.DateTimeField(auto_now_add=True)
