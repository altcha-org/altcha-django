from __future__ import annotations

from rest_framework import serializers

from altcha_django.contrib.rest_framework import AltchaField


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    message = serializers.CharField()
    altcha = AltchaField(bind_fields=["email"])
