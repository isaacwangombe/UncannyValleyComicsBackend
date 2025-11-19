from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings

from .models import ContactMessage, MailingListSubscriber
from .serializers import ContactMessageSerializer, MailingListSerializer

unsubscribe_url = "https://uncannyvalleycomics.com/unsubscribe/?email={email}"

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
        ["inmariga@gmail.com"],
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

    unsubscribe_template = (
        "\n\n---\n"
        "To unsubscribe from our mailing list, click here:\n"
        "https://uncannyvalleycomics.com/unsubscribe/?email={email}\n"
    )

    for email in emails:
        try:
            sub = MailingListSubscriber.objects.get(email=email)
            first = sub.first_name or ""
            last = sub.last_name or ""
        except MailingListSubscriber.DoesNotExist:
            first = ""
            last = ""

        # ALWAYS have a fallback:
        name = (f"{first} {last}".strip() or first or last or email.split("@")[0])

        print("Sending to:", email, "| First:", first, "| Last:", last, "| Name:", name)

        # Replace merge tags
        rendered_body = (
            body.replace("{{name}}", name)
                .replace("{{first_name}}", first)
                .replace("{{last_name}}", last)
        )

        content = rendered_body + unsubscribe_template.format(email=email)

        send_mail(
            subject,
            content,
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )

    return Response({"success": True})





@api_view(["POST"])
@permission_classes([IsAdminUser])
def reply_to_message(request, pk):
    try:
        msg = ContactMessage.objects.get(pk=pk)
    except ContactMessage.DoesNotExist:
        return Response({"error": "Message not found"}, status=404)

    subject = request.data.get("subject")
    body = request.data.get("body")

    if not subject or not body:
        return Response({"error": "Missing subject or body"}, status=400)
    unsubscribe_template = (
    "\n\n---\n"
    "To unsubscribe from our mailing list, click here:\n"
    "https://uncannyvalleycomics.com/unsubscribe/?email={email}\n"
    )

    body_with_unsubscribe = body + unsubscribe_template.format(email=msg.email)
    # Send reply
    send_mail(
        subject,
        body_with_unsubscribe,
        settings.DEFAULT_FROM_EMAIL,
        [msg.email],
        fail_silently=False,
    )

    # Mark this SPECIFIC message as replied
    msg.replied = True
    msg.save(update_fields=["replied"])

    return Response({"success": True})



# -----------------------------------------
# Admin: Get mailing list
# -----------------------------------------
@api_view(["GET"])
@permission_classes([IsAdminUser])
def mailing_list(request):
    subs = MailingListSubscriber.objects.order_by("-subscribed_at")
    return Response(MailingListSerializer(subs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def unsubscribe(request):
    email = request.GET.get("email")

    if not email:
        return Response({"error": "Email missing"}, status=400)

    try:
        sub = MailingListSubscriber.objects.get(email=email)
        sub.delete()
        return Response({"success": True, "message": "Unsubscribed"})
    except MailingListSubscriber.DoesNotExist:
        return Response({"error": "Not found"}, status=404)


@api_view(["POST"])
@permission_classes([AllowAny])
def subscribe_to_mailing_list(request):
    email = request.data.get("email")
    first_name = request.data.get("first_name", "").strip()
    last_name = request.data.get("last_name", "").strip()

    if not email:
        return Response({"error": "Email is required"}, status=400)

    sub, created = MailingListSubscriber.objects.get_or_create(email=email)

    # Always update names (even if already subscribed)
    if first_name:
        sub.first_name = first_name
    if last_name:
        sub.last_name = last_name
    sub.save()

    return Response({
        "subscribed": created,
        "first_name": sub.first_name,
        "last_name": sub.last_name,
        "message": "Subscribed successfully" if created else "Already subscribed"
    })


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_subscriber(request, pk):
    try:
        sub = MailingListSubscriber.objects.get(pk=pk)
        sub.delete()
        return Response({"success": True})
    except MailingListSubscriber.DoesNotExist:
        return Response({"error": "Not found"}, status=404)
