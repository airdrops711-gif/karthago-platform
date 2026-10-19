# Karthago Platform — Detailed Development Plan

## Current Status
- **Repo**: `/home/ubuntu/.nanobot/workspace/karthago-platform` (Django/HTMX/Tailwind)
- **OpenShift pod**: `dropship-web` (running, 2/2 pods ready)
- **Route**: `https://dropship-route-saif711-dev.apps.rm3.7wse.p1.openshiftapps.com`

## Issues Identified

### 1. No Dynamic Categories
- Templates have hardcoded category lists
- Backend has Category model but frontend doesn't fetch from API
- **Fix**: Fetch categories from `/api/v1/catalog/category-tree/` and render dynamically

### 2. Search Not Working Properly
- HTMX search endpoint `/search/` exists in backend
- Frontend has search form but results may not display correctly
- **Fix**: Ensure HTMX `hx-get` targets correct element, add no-results state

### 3. Cart Not Working
- No cart model/frontend integration
- AddToCart buttons exist but no cart page or state management
- **Fix**: Add cart context (localStorage), cart page, and HTMX add-to-cart buttons

### 4. Limited Scraped Products
- Only ~11 seed products + some from quickk.tn scraping
- Sources: jumia.tn, makino.tn, amazon.ma (DNS/Cloudflare issues)
- Need more Tunisian/Arab e-commerce sources
- **Fix**: Add souq.com, noon.com, add category-specific selectors, improve image extraction

### 5. Missing Filters
- No price range filters on product listing
- No stock filter working properly
- No brand/sort filters
- **Fix**: Add price min/max query params to API, add stock filter UI, add sort dropdown

## Phase 1: Cart & Checkout Integration

### Files to Create/Modify
1. `apps/orders/models.py` — Add Cart model (optional) or use localStorage only
2. `apps/core/context_processors.py` — Add cart item count to all templates
3. `templates/storefront/nav.html` — Add cart badge with HTRX badge count
4. `templates/storefront/partials/_product_card.html` — Add AddToCart HTMX button
5. `apps/orders/views.py` — Enhance CheckoutView to accept cart items
6. `templates/storefront/checkout.html` — One-step checkout form

### Tasks
- [ ] Add HTMX add-to-cart button to product cards
- [ ] Add cart badge to navigation showing item count from localStorage
- [ ] Create minimal cart page using localStorage
- [ ] Wire HTMX `hx-post` to `/api/v1/orders/checkout/` with cart data

## Phase 2: Dynamic Categories & Filters

### Files to Create/Modify
1. `apps/catalog/views.py` — Add `get_categories_tree()` returning HTML partial
2. `templates/storefront/partials/_category_tree.html` — Already exists, ensure it works
3. `templates/storefront/index.html` — Replace hardcoded categories with `{% include %}` from view context
4. `apps/catalog/views.py` — Add price filter, stock filter to `ProductListView.get_queryset()`
5. `templates/storefront/index.html` — Add price range buttons, stock checkbox
6. `apps/api.py` or `backend/` — Add search/filter endpoints if needed

### Tasks
- [ ] Fetch categories from backend API in product list view
- [ ] Add price filter buttons (0-50, 50-150, 150+ DT)
- [ ] Add "En stock uniquement" checkbox that filters `stock > 0`
- [ ] Add sort dropdown (nouveautés, prix croissant, prix décroissant)
- [ ] Ensure category filter passes `?category=slug` to queryset

## Phase 3: Search Enhancement

### Files to Create/Modify
1. `apps/catalog/views.py` — Enhance `product_search()` with better filtering
2. `templates/storefront/partials/_search_results.html` — Already exists, improve styling
3. `templates/storefront/nav.html` — Improve instant search results overlay
4. `templates/storefront/index.html` — Add search bar header section

### Tasks
- [ ] Ensure HTMX search `hx-get` to `/search/` with query param
- [ ] Add debounced search (250ms delay)
- [ ] Display no-results state when query returns nothing
- [ ] Add search suggestions/category refinement

## Phase 4: Scraping Engine Improvements

### Files to Create/Modify
1. `apps/scraper/models.py` — Add more ScrapedSource entries with proper selectors
2. `apps/scraper/engines.py` — Improve HTTPEngine image extraction (data-src support already exists)
3. `apps/scraper/tasks.py` — Improve product saving with category mapping
4. `apps/scraper/views.py` — Add source management UI
5. `templates/dashboard/scrapers.html` — Already exists, improve source list

### Tasks
- [ ] Add 3-5 new Tunisian e-commerce sources with correct CSS selectors
- [ ] Improve image extraction to prefer `data-src` over `src` (already partially done)
- [ ] Add brand/model extraction from product pages
- [ ] Add category mapping per source
- [ ] Schedule periodic scraping via Celery beat

## Phase 5: Deployment & Verification

### OpenShift Commands
```bash
# 1. Make migrations after model changes
cd /home/ubuntu/.nanobot/workspace/karthago-platform
source venv/bin/activate
python manage.py makemigrations
python manage.py migrate

# 2. Collect static
python manage.py collectstatic

# 3. Build and deploy to OpenShift
# Update deployment config with new image
oc set env dc/dropship-web PYTHONPATH=/app:/home/ubuntu/.nanobot/workspace/karthago-platform
oc rollout latest dc/dropship-web

# 4. Verify
curl -s https://dropship-route-saif711-dev.apps.rm3.7wse.p1.openshiftapps.com/ | head -30
```

### Definition of Done
- [ ] Categories load dynamically from DB (7 categories)
- [ ] Search works: type query, see products, filter by category
- [ ] Cart: Add to cart works, badge shows count, cart page accessible
- [ ] Price filters apply correctly to product grid
- [ ] Stock filter shows only in-stock products
- [ ] Scraping adds 50+ new products from additional sources
- [ ] OpenShift route returns 200 with all features working

## Priority Order
1. **Phase 1** — Cart integration (blocks checkout)
2. **Phase 2** — Categories + filters (blocks product discovery)
3. **Phase 3** — Search enhancement
4. **Phase 4** — Scraping expansion (grows catalog)
5. **Phase 5** — Deploy & verify on OpenShift
