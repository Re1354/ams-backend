from rest_framework import serializers


class APIInfoResponseSerializer(serializers.Serializer):
    """Serializer for API information response"""
    name = serializers.CharField()
    version = serializers.CharField()
    description = serializers.CharField()
    documentation = serializers.DictField()
    endpoints = serializers.DictField()
    features = serializers.ListField(child=serializers.CharField())