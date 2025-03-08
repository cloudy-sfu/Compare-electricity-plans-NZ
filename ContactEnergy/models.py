from django.db import models

# Create your models here.
class ContactEnergyMeter(models.Model):
    account_number = models.CharField(max_length=32)
    contract_id = models.CharField(max_length=32)

    def __str__(self):
        return f"Account number: {self.account_number}, Contract ID: {self.contract_id}"

class ContactEnergySession(models.Model):
    meter = models.ForeignKey(ContactEnergyMeter, on_delete=models.CASCADE)
    finished_dates = models.SmallIntegerField(default=0)
    failed_dates = models.SmallIntegerField(default=0)
    total_dates = models.SmallIntegerField(default=0)
    auth = models.CharField(max_length=200)
    csrf_token = models.CharField(max_length=200)
    uuid = models.CharField(max_length=200)
    created_time = models.DateTimeField(auto_now_add=True)
