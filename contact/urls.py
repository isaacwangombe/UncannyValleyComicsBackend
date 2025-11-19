from django.urls import path
from . import views


print("CONTACT URLS LOADED ✔")

urlpatterns = [
    path("send/", views.send_contact_message, name="contact_send"),
    
    path("unsubscribe/", views.unsubscribe, name="unsubscribe"),
    path("subscribe/", views.subscribe_to_mailing_list, name="contact_subscribe"),
    path("admin/mailing-list/<int:pk>/delete/", views.delete_subscriber),

    # Admin endpoints
    path("admin/messages/", views.list_messages, name="contact_admin_messages"),
    path("admin/message/<int:pk>/reply/", views.reply_to_message, name="contact_reply_message"),
    path("admin/mailing-list/", views.mailing_list, name="contact_admin_mailing_list"),
    path("admin/email-blast/", views.send_email_blast, name="contact_admin_email_blast"),
]
