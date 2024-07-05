from django.db import models

# Create your models here.
class PDFFile(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class PageConnection(models.Model):
    pdf_file = models.ForeignKey(PDFFile, on_delete=models.CASCADE)
    source_page = models.IntegerField()
    target_page = models.IntegerField()
    similarity = models.FloatField()

"""
db migration
python manage.py makemigrations
python manage.py migrate
"""
