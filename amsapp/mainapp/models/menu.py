from django.db import models


class Menu(models.Model):
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=100, blank=True, null=True)   # for frontend icons
    link = models.CharField(max_length=255)
    component = models.CharField(max_length=255)                          # frontend route

    class Meta:
        db_table = "menus"

    def __str__(self):
        return self.label
