from django.urls import include, path
urlpatterns = [path('', include('budget.urls'))]
handler403 = 'budget.views.forbidden_view'
handler404 = 'budget.views.not_found_view'
handler500 = 'budget.views.server_error_view'
