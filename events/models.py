# events/models.py
from django.db import models
from django.conf import settings

class Event(models.Model):
    title = models.CharField(max_length=250)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=250, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.title

class EventTicket(models.Model):
    event = models.ForeignKey(Event, related_name="tickets", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tickets", on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey("orders.Order", related_name="event_tickets", on_delete=models.SET_NULL, null=True, blank=True)
    bought_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self): return f"Ticket {self.pk} for {self.event.title}"
