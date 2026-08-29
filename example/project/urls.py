from __future__ import annotations

from django.urls import include, path

from contact import views

urlpatterns = [
    path("", views.contact, name="contact"),
    path("formset/", views.contact_formset, name="contact-formset"),
    path("api/contact/", views.ContactAPI.as_view(), name="contact-api"),
    path("stats/", views.stats, name="stats"),
    path("altcha/", include("altcha_django.urls")),
]
