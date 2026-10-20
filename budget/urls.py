from django.urls import path
from . import views
urlpatterns = [
    path('static/budget/<str:name>', views.public_asset),
    path('', views.family_gate, name='home'),
    path('innlogging/', views.login_view, name='login'), path('kode/', views.verify_view, name='verify'),
    path('passord/', views.password_view, name='password_login'), path('passord/endre/', views.password_change_view, name='password_change'),
    path('registrer/medlem/', views.register_account_view, name='register_member'),
    path('registrer/familie/', views.register_account_view, {'new_household': True}, name='register_household'),
    path('familieport/', views.family_gate, name='family_gate'), path('utlogging/', views.logout_view, name='logout'),
    path('invitasjon/<str:token>/', views.invitation_view, name='invitation'),
    path('app/<str:page>/', views.page_view, name='page'),
    path('ny/<str:kind>/', views.edit_view, name='create'), path('endre/<str:kind>/<uuid:row_id>/', views.edit_view, name='edit'),
    path('slett/<uuid:row_id>/', views.delete_view, name='delete'), path('betal/<uuid:row_id>/', views.pay_view, name='pay'),
    path('preferanser/', views.preferences_view, name='preferences'), path('inviter/', views.invite_view, name='invite'), path('tilbakekall/<uuid:row_id>/', views.revoke_view, name='revoke'),
    path('gjeldsplan/', views.debt_plan_view, name='debt_plan'),
    path('import/bekreft/', views.import_view, name='apply_import'), path('import/avklar/<uuid:row_id>/', views.resolve_import, name='resolve_import'),
    path('manifest.webmanifest', views.manifest_view), path('sw.js', views.worker_view), path('offline/', views.offline_view), path('info/<str:topic>/', views.help_view, name='info'),
]
