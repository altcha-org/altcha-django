"""URL patterns for the (optional) challenge endpoints.

::

    path("altcha/", include("altcha_django.urls")),
"""

from __future__ import annotations

from django.urls import path

from .views import ChallengeView, SentinelChallengeProxyView

app_name = "altcha_django"

urlpatterns = [
    path("challenge/", ChallengeView.as_view(), name="challenge"),
    path(
        "sentinel/challenge/",
        SentinelChallengeProxyView.as_view(),
        name="sentinel-challenge",
    ),
]
