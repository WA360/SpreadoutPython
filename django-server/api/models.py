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
    pdf_file = models.ForeignKey(
        PDFFile, on_delete=models.CASCADE)
    group = models.IntegerField(null=True)


class PageConnection(models.Model):
    pdf_file = models.ForeignKey(
        PDFFile, on_delete=models.CASCADE)
    source = models.ForeignKey(
        Chapter,
        related_name="source_connections",
        on_delete=models.CASCADE,
        db_column="source",
    )
    target = models.ForeignKey(
        Chapter,
        related_name="target_connections",
        on_delete=models.CASCADE,
        db_column="target",
    )
    similarity = models.FloatField()


# 메세지 관련 모델
class Session(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="user")
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, db_column="chapter")


class Message(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, db_column="session")
    sender = models.CharField(max_length=10, choices=[("user", "User"), ("bot", "Bot")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


"""
db migration
python manage.py makemigrations
python manage.py migrate
"""
