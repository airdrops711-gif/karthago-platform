from django.urls import path
from . import seo

app_name = "seo"

urlpatterns = [
    path("robots.txt", seo.robots_txt, name="robots"),
    path("sitemap.xml", seo.sitemap, name="sitemap"),
]
