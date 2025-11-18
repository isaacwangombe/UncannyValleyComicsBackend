from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings

from .models import ContactMessage, MailingListSubscriber
from .serializers import ContactMessageSerializer, MailingListSerializer


# -----------------------------------------
# Public Contact Form Submission
# -----------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
def send_contact_message(request):
    print("CONTACT FORM RECEIVED:", request.data)  # ⬅ ADD THIS

    serializer = ContactMessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    msg = serializer.save()

    # Email notification to you
    send_mail(
        f"New Contact Message From: {msg.email}",
        msg.message,
        settings.DEFAULT_FROM_EMAIL,
        ["uvcomicbooks@gmail.com"],
    )

    return Response({"success": True})


# -----------------------------------------
# Admin: View all messages
# -----------------------------------------
@api_view(["GET"])
@permission_classes([IsAdminUser])
def list_messages(request):
    messages = ContactMessage.objects.order_by("-created_at")
    return Response(ContactMessageSerializer(messages, many=True).data)


# -----------------------------------------
# Admin: Email blast
# -----------------------------------------
@api_view(["POST"])
@permission_classes([IsAdminUser])
def send_email_blast(request):
    subject = request.data.get("subject")
    body = request.data.get("body")
    emails = request.data.get("emails")

    if not subject or not body or not emails:
        return Response({"error": "Missing fields"}, status=400)

    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        emails,
    )

    return Response({"success": True})


# -----------------------------------------
# Admin: Get mailing list
# -----------------------------------------
@api_view(["GET"])
@permission_classes([IsAdminUser])
def mailing_list(request):
    subs = MailingListSubscriber.objects.order_by("-subscribed_at")
    return Response(MailingListSerializer(subs, many=True).data)
