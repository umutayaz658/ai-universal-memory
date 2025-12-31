from django.contrib import admin
from .models import Project, Memory

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'id')
    list_filter = ('user', 'created_at')
    search_fields = ('name', 'user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'short_text', 'category', 'created_at')
    list_filter = ('project__user', 'project', 'category', 'created_at')
    # Removed 'raw_text' from search because it is now encrypted and cannot be searched by DB
    search_fields = ('tags', 'project__name')
    ordering = ('-created_at',)
    
    # 🛡️ THE CRASH-PROOF FIX 🛡️
    # Exclude the vector field from the change form entirely.
    # This prevents Django from performing the ambiguous truth check that causes the 500 error.
    exclude = ('vector',) 
    readonly_fields = ('created_at',)

    def short_text(self, obj):
        if obj.raw_text and len(obj.raw_text) > 60:
            return obj.raw_text[:60] + "..."
        return obj.raw_text
    short_text.short_description = 'Content Preview'
