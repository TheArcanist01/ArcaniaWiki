from django.urls import path
from . import views

app_name = "arcaniawiki"

urlpatterns = [
    path("", views.article_list, name="article_list"),
    path(
        "articles/<slug:slug>/",
        views.article_detail,
        name="article_detail"
    ),
]