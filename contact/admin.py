from django.contrib import admin
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages

from .models import ContactMessage, MailingListSubscriber


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "created_at", "replied")
    search_fields = ("email", "first_name", "last_name", "message")
    list_filter = ("replied", "created_at")
    readonly_fields = ("first_name", "last_name", "email", "message", "created_at")

    actions = ["send_reply"]

    def send_reply(self, request, queryset):
        for msg in queryset:
            if not msg.reply_text:
                messages.error(request, f"Message from {msg.email} has no reply text.")
                continue

            send_mail(
                subject="Reply from Uncanny Valley Comics",
                message=msg.reply_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[msg.email],
            )

            msg.replied = True
            msg.save()

        self.message_user(request, "Replies sent successfully.")


@admin.register(MailingListSubscriber)
class MailingListAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "subscribed_at")
    search_fields = ("email", "first_name", "last_name")

    actions = ["send_email_blast"]

    def send_email_blast(self, request, queryset):
        subject = request.POST.get("_subject")
        body = request.POST.get("_body")

        if not subject or not body:
            self.message_user(request, "Subject and message body are required.", level="error")
            return

        emails = [s.email for s in queryset]

        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

        self.message_user(request, "Email blast sent successfully.")


    # Add extra fields for subject & body
    class Media:
        js = ("admin/emailblast.js",)  # We’ll create this JS popup
