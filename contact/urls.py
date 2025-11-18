from django.urls import path
from . import views

urlpatterns = [
    path("send/", views.send_contact_message, name="contact_send"),
    
    # Admin endpoints
    path("admin/messages/", views.list_messages, name="contact_admin_messages"),
    path("admin/mailing-list/", views.mailing_list, name="contact_admin_mailing_list"),
    path("admin/email-blast/", views.send_email_blast, name="contact_admin_email_blast"),
]
