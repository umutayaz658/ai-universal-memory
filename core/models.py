import uuid
from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Memory(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memories')
    raw_text = models.TextField()
    vector = VectorField(dimensions=768)  # Using 768 dimensions as requested
    tags = models.JSONField(default=list, blank=True)
    
    # NEW FIELD
    category = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Memory for {self.project.name} ({self.created_at})"

class ProjectReport(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    markdown_content = models.TextField()
    data_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.project.name} ({self.created_at})"
