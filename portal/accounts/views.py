# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from portal.accounts.models import Account, Business


class LoginForm(AuthenticationForm):
    def clean_username(self) -> str:
        return (
            self.cleaned_data["username"].strip().lower()
        )  # emails are stored in lower case


class ResetForm(PasswordResetForm):
    def get_users(self, email):
        # Django's form skips an account with no password yet, which would leave an invitee with an expired link stuck.
        return Account.objects.filter(email__iexact=email, is_active=True)


class Login(auth.LoginView):
    authentication_form = LoginForm
    redirect_authenticated_user = True


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/home.html")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "accounts/dashboard.html",
        {"business": Business.objects.filter(account=request.user).first()},
    )
