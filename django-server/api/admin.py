from django.contrib import admin
from .models import PDFFile, PageConnection

@admin.register(PDFFile)
class PDFFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'filename', 'uploaded_at')

@admin.register(PageConnection)
class PageConnectionAdmin(admin.ModelAdmin):
    list_display = ('pdf_file', 'source_page', 'target_page', 'similarity')
