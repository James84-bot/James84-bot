from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("branches", views.BranchViewSet, basename="branch")
router.register("members", views.MemberViewSet, basename="member")
router.register("invitations", views.InvitationViewSet, basename="invitation")

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/password/change/", views.PasswordChangeView.as_view(), name="auth-password-change"),
    path("auth/password/reset/", views.PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("auth/password/reset/confirm/", views.PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("auth/invitations/accept/", views.AcceptInvitationView.as_view(), name="auth-invitation-accept"),
    path("auth/invitations/<str:token>/", views.InvitationPreviewView.as_view(), name="auth-invitation-preview"),
    path("organization/", views.OrganizationView.as_view(), name="organization"),
    *router.urls,
]
