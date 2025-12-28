from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Project, Memory

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'email')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', '')
        )
        return user

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'user', 'created_at']
        read_only_fields = ['id', 'created_at', 'user']

class MemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Memory
        fields = ['id', 'project', 'raw_text', 'tags', 'source', 'created_at', 'category']
        read_only_fields = ['id', 'created_at', 'vector']
