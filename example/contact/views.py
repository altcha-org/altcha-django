from __future__ import annotations

from django.contrib import messages
from django.forms import formset_factory
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from altcha_django.results import VerificationResult

from .forms import ContactForm


def contact(request):
    form = ContactForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        result: VerificationResult = form.cleaned_data["captcha"]
        messages.success(
            request,
            f"Thanks {form.cleaned_data['name']}! "
            f"(verified via {result.payload_type}"
            + (f", score {result.score}" if result.score is not None else "")
            + ")",
        )
        return redirect("contact")
    return render(request, "contact/contact.html", {"form": form})


def contact_formset(request):
    FormSet = formset_factory(ContactForm, extra=2)
    formset = FormSet(request.POST or None, form_kwargs={"request": request})
    if request.method == "POST" and formset.is_valid():
        messages.success(request, f"{len(formset.forms)} messages accepted.")
        return redirect("contact-formset")
    return render(request, "contact/formset.html", {"formset": formset})


class ContactAPI(View):
    def post(self, request):
        try:
            from rest_framework.parsers import JSONParser
        except ImportError:
            return JsonResponse({"error": "install djangorestframework"}, status=501)
        from .serializers import ContactSerializer

        data = JSONParser().parse(request)
        serializer = ContactSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            return JsonResponse({"ok": True})
        return JsonResponse(serializer.errors, status=400)


def stats(request):
    from altcha_django.stats import recorder

    return JsonResponse(recorder.snapshot())
