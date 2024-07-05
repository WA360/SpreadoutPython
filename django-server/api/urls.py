from django.urls import path
from api.views import RecommendView

app_name = "accountapp"

urlpatterns = [
    path("recommend/", RecommendView.as_view(), name="recommend"),
]