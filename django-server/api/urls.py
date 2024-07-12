from django.urls import path
from api.views import RecommendView, SearchView

app_name = "accountapp"

urlpatterns = [
    path("recommend/", RecommendView.as_view(), name="recommend"),
    path('search/', SearchView.as_view(), name='search'),
]