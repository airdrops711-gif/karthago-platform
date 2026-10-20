"""Store settings for the vendor console.

A vendor owns its store and may edit its own public identity: the
name, the logo, the tagline, the description and the contact details.
The page is tenant-scoped: it always writes into
``request.tenant_store`` and never into another store, whatever the
posted payload says.

The commercial knobs (commission, platform-side status) are *not*
editable here: they belong to the superadmin console.
"""
import io
import os
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.catalog.models import Store, StoreLogo

#: The logo upload: a real image, small enough to be served fast.
LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOGO_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LOGO_MAX_WIDTH = 512
LOGO_MAX_HEIGHT = 512


def _is_staff(user):
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)


def _parse_decimal(raw, default):
    """Read a decimal from a form field, falling back to ``default``."""
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return default
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valeur numérique invalide : {raw}")


def _clean_logo_upload(upload):
    """Validate the uploaded logo and return its bytes and its size.

    The image is downscaled so a vendor cannot push a 4K picture into
    the storefront. Pillow is used; a broken file is rejected with a
    readable message instead of a 500.
    """
    if not upload:
        return None

    extension = os.path.splitext(upload.name)[1].lower()
    if extension not in LOGO_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ext for ext in LOGO_ALLOWED_EXTENSIONS))
        raise ValueError(
            f"Format de logo non supporté ({extension or 'inconnu'}). "
            f"Formats acceptés : {allowed}."
        )

    if upload.size > LOGO_MAX_BYTES:
        raise ValueError(
            "Le logo dépasse 2 Mo. Merci d'envoyer une image plus légère."
        )

    from PIL import Image, ImageOps

    try:
        with Image.open(upload) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            image.thumbnail((LOGO_MAX_WIDTH, LOGO_MAX_HEIGHT))
            width, height = image.size
            buffer = io.BytesIO()
            image.save(buffer, format=_pillow_format(extension))
            content_type = _content_type(extension)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types
        raise ValueError(f"Image invalide : {exc}")

    return buffer.getvalue(), content_type, width, height


def _pillow_format(extension):
    """The Pillow format matching an allowed extension."""
    return {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
    }.get(extension, "PNG")


def _content_type(extension):
    """The HTTP content type matching an allowed extension."""
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(extension, "image/png")


def uuid_name(original_name):
    """A collision-proof file name that keeps the original extension."""
    base, extension = os.path.splitext(os.path.basename(original_name))
    safe = "".join(char for char in base if char.isalnum() or char in "-_")[:40]
    return f"{safe or 'logo'}-{uuid.uuid4().hex[:12]}{extension.lower()}"


@login_required
@staff_required
def store_settings(request):
    """Edit the public identity of the tenant's store."""
    store = getattr(request, "tenant_store", None)
    if store is None:
        messages.error(
            request,
            "Aucune boutique n'est associée à votre compte.",
        )
        return redirect("dashboard:overview")

    if request.method == "POST":
        error = None

        name = (request.POST.get("name") or "").strip()
        if not name:
            error = "Le nom de la boutique est obligatoire."

        try:
            markup = _parse_decimal(
                request.POST.get("default_markup_percentage"),
                store.default_markup_percentage,
            )
            margin = _parse_decimal(
                request.POST.get("fixed_margin"), store.fixed_margin
            )
        except ValueError as exc:
            error = str(exc)
            markup, margin = store.default_markup_percentage, store.fixed_margin

        if error is None and (markup < 0 or margin < 0):
            error = "La marge et la majoration ne peuvent pas être négatives."

        logo_upload = None
        if error is None:
            try:
                logo_upload = _clean_logo_upload(request.FILES.get("logo"))
            except ValueError as exc:
                error = str(exc)

        if error is None:
            store.name = name
            store.tagline = (request.POST.get("tagline") or "").strip()
            store.description = (request.POST.get("description") or "").strip()
            store.phone_number = (request.POST.get("phone_number") or "").strip()
            store.whatsapp_number = (
                request.POST.get("whatsapp_number") or ""
            ).strip()
            store.address = (request.POST.get("address") or "").strip()
            store.default_markup_percentage = markup
            store.fixed_margin = margin
            store.save()

            # The logo: an upload wins over the URL, and the URL wins
            # over whatever was stored before. The uploaded image is
            # kept in the database (the pods are ephemeral) and served
            # by the ``store_logo`` view.
            logo_url = (request.POST.get("logo_url") or "").strip()
            if logo_upload:
                image, content_type, width, height = logo_upload
                StoreLogo.objects.update_or_create(
                    store=store,
                    defaults={
                        "image": image,
                        "content_type": content_type,
                        "width": width,
                        "height": height,
                    },
                )
                store.logo_url = reverse("store_logo", args=[store.slug])
            elif logo_url:
                store.logo_url = logo_url

            store.save()
            messages.success(
                request, "Les informations de votre boutique ont été enregistrées."
            )
            return redirect("dashboard:store_settings")

        messages.error(request, error)

    return render(
        request,
        "dashboard/store_settings.html",
        {
            "store": store,
            "storefront_url": store.storefront_url,
        },
    )
