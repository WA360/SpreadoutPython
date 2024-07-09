from django.urls import path
from api.views import RecommendView, ChatBotPipelineView

app_name = "accountapp"

urlpatterns = [
    path("recommend/", RecommendView.as_view(), name="recommend"),
    path("chat/", ChatBotPipelineView.as_view(), name="chat")
]