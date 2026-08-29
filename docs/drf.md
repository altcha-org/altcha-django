# Django REST Framework

```console
pip install 'altcha-django[drf]'
```

```python
from rest_framework import serializers
from altcha_django.contrib.rest_framework import AltchaField

class ContactSerializer(serializers.Serializer):
    email = serializers.EmailField()
    altcha = AltchaField(bind_fields=["email"])   # bind_fields -> Sentinel fieldsHash
```

Pass the request in the serializer context so request-aware backends work:

```python
ContactSerializer(data=request.data, context={"request": request})
```

- Failures raise `serializers.ValidationError` with the same `code` as the form
  field (`invalid_signature`, `replayed`, `classification_rejected`, …).
- `AltchaField(return_result=True)` puts the `VerificationResult` in
  `validated_data` instead of the raw payload.
- Async views: the field also implements `ato_internal_value` using
  `run_averification`. Stock DRF has no async serializers and never calls it —
  it exists for async-aware stacks (e.g. `adrf`) and for calling directly. Under
  plain DRF, verification runs synchronously through `to_internal_value`.
