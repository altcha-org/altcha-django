from __future__ import annotations

from django.http import HttpResponse
from django.urls import include, path

from altcha_django.views import AsyncChallengeView


def _ping(_request):
    return HttpResponse("ok")


urlpatterns = [
    path("", _ping),
    path("altcha/", include("altcha_django.urls")),
    path("altcha/async-challenge/", AsyncChallengeView.as_view(), name="async-challenge"),
]
