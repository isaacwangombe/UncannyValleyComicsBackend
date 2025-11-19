from rest_framework import serializers
from .models import ContactMessage, MailingListSubscriber

class ContactMessageSerializer(serializers.ModelSerializer):
    subscribe = serializers.BooleanField(default=False)

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "message",
            "subscribed",
            "replied",
            "created_at",
            "subscribe",
        ]
        read_only_fields = ["id", "created_at", "replied"]

    def create(self, validated_data):
        subscribe = validated_data.pop("subscribe", False)
        msg = ContactMessage.objects.create(**validated_data, subscribed=subscribe)

        if subscribe:
            MailingListSubscriber.objects.get_or_create(
                email=msg.email,
                defaults={
                    "first_name": msg.first_name,
                    "last_name": msg.last_name,
                }
            )

        return msg


class MailingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MailingListSubscriber
        fields = "__all__"
