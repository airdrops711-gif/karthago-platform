"""Product ingestion for the vendors.

Three ways to fill a store's catalogue:

* a single product form,
* a bulk CSV / XLSX import,
* an import from the central scraped pool.

Every entry point writes rows scoped to ``request.tenant_store``. A
vendor can never write into another store's catalogue, whatever the
posted payload says.
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.catalog.models import Product, Store, StoreProduct

# Columns accepted by the bulk importer.
BULK_COLUMNS = [
    "title",
    "source_cost",
    "selling_price",
    "in_stock",
    "category",
    "description",
    "image_urls",
]

TRUE_VALUES = {"1", "true", "yes", "oui", "y", "vrai", "on", "en stock", "dispo"}
FALSE_VALUES = {"0", "false", "no", "non", "n", "faux", "off", "rupture", "hors stock"}


def _is_staff(user):
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)


# ---------------------------------------------------------------------------
# Price normalisation
# ---------------------------------------------------------------------------
def parse_tunisian_price(raw):
    """Parse a Tunisian price into a Decimal with 3 decimals.

    Accepts every format seen on the Tunisian suppliers:
    ``"12,500"``, ``"12.500"``, ``"12 500,000"``, ``"45.500 DT"``,
    ``"1 169,000 DT"``, ``"1299"``.

    The rules follow the Tunisian commercial writing:

    * a comma is the decimal separator — ``"12,500"`` is 12.500 DT;
    * a dot is the thousands separator — ``"45.500"`` is 45 500 DT;
    * a dot on a number of four digits or more carries the millimes —
      ``"1299.000"`` is 1299.000 DT;
    * a space is a thousands separator — ``"12 500,000"`` is 12 500 DT.
    """
    if raw is None:
        raise ValueError("Prix manquant")
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw)).quantize(Decimal("0.001"))

    text = str(raw).strip()
    # Drop the currency and any unit suffix.
    text = re.sub(r"(?i)\b(dt|tnd|dh|dinars?|tunisie?)\b", "", text)
    text = text.replace(" ", " ").strip()
    if not text:
        raise ValueError("Prix manquant")

    negative = text.startswith("-")
    text = text.lstrip("-+")

    # Keep only digits and separators.
    text = re.sub(r"[^\d.,]", "", text)
    if not text:
        raise ValueError(f"Prix illisible: {raw!r}")

    has_comma = "," in text
    has_dot = "." in text

    if has_comma and has_dot:
        # The right-most separator is the decimal one.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        # A single comma is the decimal separator in Tunisia.
        text = text.replace(",", ".")
    elif has_dot:
        if re.fullmatch(r"\d{1,3}\.\d{3}", text):
            # One to three digits before the dot: the dot separates the
            # thousands ("1.299" is 1299 in Tunisia).
            text = text.replace(".", "")
        elif re.fullmatch(r"\d{4,}\.\d{3}", text):
            # Four digits or more: the dot carries the millimes
            # ("1299.000" is 1299.000 DT).
            pass
        else:
            text = text.replace(".", "")

    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Prix illisible: {raw!r}")

    if negative:
        value = -value
    return value.quantize(Decimal("0.001"))


def parse_bool(raw, default=True):
    """Parse a truthy cell from a spreadsheet."""
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def split_image_urls(raw):
    """Split a cell holding one or several image URLs."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    parts = re.split(r"[;|\n]", str(raw))
    return [part.strip() for part in parts if part.strip()]


# ---------------------------------------------------------------------------
# Single product
# ---------------------------------------------------------------------------
class ProductCreateView(View):
    """Create one product in the vendor's own store."""

    @login_required
    @staff_required
    def get(self, request):
        store = getattr(request.user, "store", None)
        context = {
            "store": store,
            "products": (
                StoreProduct.objects.filter(store=store).order_by("-created_at")[:50]
                if store else []
            ),
        }
        return render(request, "dashboard/products.html", context)

    @login_required
    @staff_required
    def post(self, request):
        store = getattr(request.user, "store", None)
        if store is None:
            messages.error(request, "Aucun magasin n'est associé à votre compte.")
            return redirect("dashboard:product_create")

        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        category = (request.POST.get("category") or "").strip()
        image_url = (request.POST.get("image_url") or "").strip()

        errors = []
        if not title:
            errors.append("Le titre est obligatoire.")

        try:
            source_cost = parse_tunisian_price(request.POST.get("source_cost"))
        except ValueError as exc:
            source_cost = Decimal("0.000")
            errors.append(str(exc))

        custom_markup = None
        if (request.POST.get("custom_markup") or "").strip():
            try:
                custom_markup = Decimal(request.POST["custom_markup"].strip())
            except (InvalidOperation, ValueError):
                errors.append("Marge invalide.")

        selling_price = None
        if (request.POST.get("selling_price") or "").strip():
            try:
                selling_price = parse_tunisian_price(request.POST["selling_price"])
            except ValueError as exc:
                errors.append(str(exc))

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("dashboard:product_create")

        product = StoreProduct(
            store=store,
            title=title,
            description=description,
            category=category,
            source_cost=source_cost,
            custom_markup=custom_markup,
            in_stock=parse_bool(request.POST.get("in_stock"), True),
            is_published=parse_bool(request.POST.get("is_published"), True),
            is_store_native=True,
            image_url=image_url,
        )
        if selling_price is not None:
            product.selling_price = selling_price
        product.save()

        messages.success(request, f"Produit « {product.title} » ajouté à {store.name}.")
        return redirect("dashboard:product_create")


class ProductUpdateView(View):
    """Edit or unpublish one product of the vendor's store."""

    @login_required
    @staff_required
    def post(self, request, product_id):
        store = getattr(request.user, "store", None)
        product = get_object_or_404(StoreProduct, pk=product_id, store=store)

        action = (request.POST.get("action") or "").strip()
        if action == "toggle_published":
            product.is_published = not product.is_published
            product.save(update_fields=["is_published", "updated_at"])
            messages.success(
                request,
                "Produit publié." if product.is_published else "Produit retiré de la vitrine.",
            )
        elif action == "toggle_stock":
            product.in_stock = not product.in_stock
            product.save(update_fields=["in_stock", "updated_at"])
            messages.success(
                request,
                "Produit en stock." if product.in_stock else "Produit marqué en rupture.",
            )
        return redirect("dashboard:product_create")


class ProductDeleteView(View):
    """Delete one product of the vendor's store."""

    @login_required
    @staff_required
    def post(self, request, product_id):
        store = getattr(request.user, "store", None)
        product = get_object_or_404(StoreProduct, pk=product_id, store=store)
        title = product.title
        product.delete()
        messages.success(request, f"Produit « {title} » supprimé.")
        return redirect("dashboard:product_create")


# ---------------------------------------------------------------------------
# Bulk ingestion
# ---------------------------------------------------------------------------
def _read_rows(file_obj, filename):
    """Yield the header + rows of a CSV or an XLSX file.

    The XLSX branch uses openpyxl when it is available; a missing
    dependency degrades to a clear error instead of a crash.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError:
            raise ValueError(
                "La lecture des fichiers .xlsx requiert openpyxl "
                "(pip install openpyxl) ou l'import d'un fichier CSV."
            )
        workbook = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        sheet = workbook.active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        workbook.close()
    else:
        text = file_obj.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))

    rows = [row for row in rows if any(str(cell).strip() for cell in row)]
    if not rows:
        return [], []
    header = [str(cell).strip().lower() for cell in rows[0]]
    return header, rows[1:]


def _cell(header, row, column, aliases=()):
    """Read a cell by column name, with a few accepted aliases."""
    names = [column, *aliases]
    for name in names:
        if name in header:
            index = header.index(name)
            if index < len(row):
                return row[index]
    return None


def import_bulk_rows(store, header, rows):
    """Create the products of a bulk file. Returns (imported, errors).

    The whole batch is written in one transaction: a malformed line
    aborts the import instead of leaving half a catalogue behind.
    """
    imported = 0
    errors = []

    for number, row in enumerate(rows, start=2):
        title = _cell(header, row, "title", ("nom", "produit", "name"))
        title = (str(title).strip() if title is not None else "")
        if not title:
            errors.append({"line": number, "message": "Titre manquant."})
            continue

        try:
            cost_raw = _cell(header, row, "source_cost", ("cost", "prix_source", "prix d'achat", "prix achat"))
            source_cost = parse_tunisian_price(cost_raw)
        except ValueError as exc:
            errors.append({"line": number, "message": str(exc)})
            continue

        selling_price = None
        price_raw = _cell(header, row, "selling_price", ("prix", "prix_vente", "prix de vente"))
        if price_raw is not None and str(price_raw).strip():
            try:
                selling_price = parse_tunisian_price(price_raw)
            except ValueError as exc:
                errors.append({"line": number, "message": str(exc)})
                continue

        in_stock = parse_bool(_cell(header, row, "in_stock", ("stock", "disponible")), True)
        category = str(_cell(header, row, "category", ("categorie", "catégorie")) or "").strip()
        description = str(_cell(header, row, "description", ("desc")) or "").strip()
        image_urls = split_image_urls(_cell(header, row, "image_urls", ("image", "images", "url")))

        product = StoreProduct(
            store=store,
            title=title,
            description=description,
            category=category,
            source_cost=source_cost,
            in_stock=in_stock,
            is_published=True,
            is_store_native=True,
            image_url=image_urls[0] if image_urls else "",
            image_urls=image_urls,
        )
        if selling_price is not None:
            product.selling_price = selling_price
        product.save()
        imported += 1

    return imported, errors


class BulkImportView(View):
    """Bulk ingestion from a CSV or an XLSX file."""

    @login_required
    @staff_required
    def get(self, request):
        store = getattr(request.user, "store", None)
        context = {
            "store": store,
            "columns": BULK_COLUMNS,
        }
        return render(request, "dashboard/products_bulk.html", context)

    @login_required
    @staff_required
    def post(self, request):
        store = getattr(request.user, "store", None)
        if store is None:
            messages.error(request, "Aucun magasin n'est associé à votre compte.")
            return redirect("dashboard:product_bulk")

        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Aucun fichier reçu.")
            return redirect("dashboard:product_bulk")

        try:
            header, rows = _read_rows(upload, upload.name)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:product_bulk")

        if not header:
            messages.error(request, "Le fichier est vide.")
            return redirect("dashboard:product_bulk")

        missing = [column for column in ("title", "source_cost") if column not in header]
        if missing:
            messages.error(
                request,
                "Colonnes manquantes dans le fichier: " + ", ".join(missing),
            )
            return redirect("dashboard:product_bulk")

        try:
            with transaction.atomic():
                imported, errors = import_bulk_rows(store, header, rows)
        except Exception as exc:
            messages.error(request, f"Import annulé: {type(exc).__name__}: {exc}")
            return redirect("dashboard:product_bulk")

        if request.headers.get("HX-Request"):
            return render(
                request,
                "dashboard/partials/_bulk_result.html",
                {"imported": imported, "errors": errors, "total": len(rows)},
            )

        if imported:
            messages.success(request, f"{imported} produit(s) importé(s) dans {store.name}.")
        for error in errors[:10]:
            messages.error(request, f"Ligne {error['line']}: {error['message']}")
        return redirect("dashboard:product_bulk")


# ---------------------------------------------------------------------------
# Import from the central scraped pool
# ---------------------------------------------------------------------------
class ImportFromPoolView(View):
    """Clone products of the central scraped pool into the vendor's store."""

    @login_required
    @staff_required
    def get(self, request):
        from apps.catalog.tenancy import central_pool

        query = (request.GET.get("q") or "").strip()
        store = getattr(request.user, "store", None)
        context = {
            "store": store,
            "products": central_pool(search=query, limit=100),
            "q": query,
        }
        return render(request, "dashboard/products_import.html", context)

    @login_required
    @staff_required
    def post(self, request):
        store = getattr(request.user, "store", None)
        if store is None:
            messages.error(request, "Aucun magasin n'est associé à votre compte.")
            return redirect("dashboard:product_import")

        product_ids = request.POST.getlist("product_ids")
        if not product_ids:
            messages.error(request, "Aucun produit sélectionné.")
            return redirect("dashboard:product_import")

        imported = 0
        for product_id in product_ids:
            if not str(product_id).isdigit():
                continue
            source = Product.objects.filter(pk=int(product_id), is_active=True).first()
            if source is None:
                continue
            if StoreProduct.objects.filter(
                store=store, scraped_source_product=source
            ).exists():
                continue

            images = [img.url for img in source.images.all() if img.url]
            clone = StoreProduct(
                store=store,
                scraped_source_product=source,
                title=source.title,
                description=source.description,
                category=source.category.name if source.category else "",
                source_cost=source.raw_cost,
                selling_price=source.retail_price,
                image_url=images[0] if images else "",
                image_urls=images,
                external_url=source.source,
                in_stock=source.stock > 0,
                is_published=True,
                is_store_native=False,
            )
            clone.save()
            imported += 1

        messages.success(request, f"{imported} produit(s) importé(s) dans votre magasin.")
        return redirect("dashboard:product_import")
