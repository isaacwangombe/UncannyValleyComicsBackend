# accounts/serializers.py
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


# --- REGISTER SERIALIZER ---
class CustomRegisterSerializer(RegisterSerializer):
    username = None  # hide username input

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data["username"] = data.get("email")  # auto-fill username = email
        return data


# --- USER DETAILS SERIALIZER (with Owner role support) ---
class CustomUserDetailsSerializer(UserDetailsSerializer):
    role = serializers.SerializerMethodField()

    class Meta(UserDetailsSerializer.Meta):
        model = User
        fields = (
            "pk",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "role",
        )

    def get_role(self, obj):
        print(f"🔍 get_role called for {obj.email}")
        if obj.is_superuser:
            return "Superadmin"
        elif obj.groups.filter(name="Owner").exists():
            return "Owner"
        elif obj.is_staff:
            return "Staff"
        return "Customer"
