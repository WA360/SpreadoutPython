from django.db import models
from django.contrib.auth.models import User

class PDFFile(models.Model):
    filename = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    url = models.URLField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Chapter(models.Model):
    name = models.CharField(max_length=255)
    start_page = models.IntegerField()
    end_page = models.IntegerField()
    level = models.IntegerField()
    bookmarked = models.BooleanField(default=False)
    pdf_file = models.ForeignKey(PDFFile, on_delete=models.CASCADE)

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
