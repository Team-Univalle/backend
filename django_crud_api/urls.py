from django.contrib import admin
from django.urls import path

from tasks.views import EventDetailView, EventListCreateView, SubtaskListCreateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('events', EventListCreateView.as_view()),
    path('events/<str:pk>', EventDetailView.as_view()),
    path('events/<str:event_id>/subtasks', SubtaskListCreateView.as_view()),
]
