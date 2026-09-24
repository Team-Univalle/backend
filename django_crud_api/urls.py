from django.contrib import admin
from django.urls import path

from tasks.views import EventDetailView, EventListCreateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('events', EventListCreateView.as_view()),
    path('events/<str:pk>', EventDetailView.as_view()),
]
