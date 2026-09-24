from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from tasks.views import EventDetailView, EventListCreateView, SubtaskDetailView, SubtaskListCreateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('events', EventListCreateView.as_view()),
    path('events/<str:pk>', EventDetailView.as_view()),
    path('events/<str:event_id>/subtasks', SubtaskListCreateView.as_view()),
    path('subtasks/<str:pk>', SubtaskDetailView.as_view()),
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('docs', SpectacularSwaggerView.as_view(url_name='schema')),
]
