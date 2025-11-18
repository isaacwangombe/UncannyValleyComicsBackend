from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings


@api_view(["POST"])
@permission_classes([AllowAny])
def contact_message(request):
    first = request.data.get("first_name")
    last = request.data.get("last_name")
    email = request.data.get("email")
    message = request.data.get("message")

    if not all([first, last, email, message]):
        return Response({"error": "Missing fields"}, status=400)

    full_message = f"""
New message from Uncanny Valley Contact Form

From: {first} {last}
Email: {email}

Message:
{message}
"""

    send_mail(
        subject="New Contact Form Message",
        message=full_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
    )

    return Response({"success": True, "message": "Message sent!"})
