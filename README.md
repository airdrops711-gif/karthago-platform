# Karthago Commerce Platform

A modular e-commerce platform built with Django, featuring catalog management, order processing, and automated product scraping.

## Architecture

### Core Applications

- **Catalog** (`apps/catalog`) – Product catalog, inventory, and storefront
- **Orders** (`apps/orders`) – Order management, payment processing, and fulfillment
- **Scraper** (`apps/scraper`) – Automated product data collection from external sources
- **Dashboard** (`apps/dashboard`) – Admin panel for monitoring and analytics

### Key Features

- **Product Catalog** – Manage products, categories, and inventory
- **Order Management** – Create, track, and fulfill customer orders
- **Automated Scraping** – Extract product data from external websites
- **Real-time Dashboard** – Monitor sales, orders, and inventory

### Tech Stack

- **Framework**: Django 4.x
- **Database**: PostgreSQL (production) / SQLite (dev)
- **Static Files**: Whitenoise
- **Async Task Queue**: Celery
- **Message Broker**: Redis
- **Search**: Meilisearch
- **Frontend**: Tailwind CSS, HTMX
- **Deployment**: OpenShift

## Project Structure

```
karthago-platform/
├── apps/
│   ├── catalog/       # Product catalog & storefront
│   ├── orders/        # Order processing & fulfillment
│   ├── scraper/       # Automated product scraping
│   └── dashboard/     # Admin dashboard
├── config/
│   └── settings/      # Django settings (base, development, production)
├── openshift/
│   ├── imagestream.yaml  # Image streams for deployments
│   ├── configmap.yaml    # OpenShift ConfigMaps
│   ├── postgresql.yaml   # PostgreSQL configuration
│   ├── redis.yaml        # Redis configuration
│   ├── meilisearch.yaml  # Elasticsearch/Meilisearch config
│   └── service.yaml      # OpenShift services
├── templates/
│   ├── base.html        # Base template with layout
│   ├── dashboard/       # Dashboard templates
│   └── storefront/      # Storefront templates
└── requirements.txt     # Python dependencies
```

## Quick Start

1. **Environment Setup**
   ```bash
   cd karthago-platform
   source venv/bin/activate
   ```

2. **Database Migration**
   ```bash
   python manage.py migrate
   ```

3. **Collect Static Files**
   ```bash
   python manage.py collectstatic --noinput
   ```

4. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

## OpenShift Deployment

The platform is designed for OpenShift deployment with the following components:

- **Image Streams** – Pre-built Docker images for each app
- **ConfigMaps** – Application configuration
- **Services** – Internal service connectivity
- **PostgreSQL** – Primary database
- **Redis** – Cache and queue broker
- **Meilisearch** – Full-text search

See `openshift/` directory for deployment manifests.

## API Endpoints

- **Catalog** – `/api/catalog/` – Product listings and details
- **Orders** – `/api/orders/` – Order creation and management
- **Scraper** – `/api/scraper/` – Scraping jobs and results
- **Dashboard** – `/api/dashboard/` – Metrics and analytics

## Data Models

- **Product** – Name, description, price, category, inventory
- **Category** – Product classification
- **Order** – Customer orders with status and timeline
- **ScraperJob** – Automated scraping tasks

## Configuration

Key settings are in `config/settings/base.py`:
- Database connection
- Static file serving
- Template configuration
- Third-party integrations

## Testing

```bash
# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Check for issues
python manage.py check

# Run tests (if any)
python manage.py test
```

## Deployment

Deploy to OpenShift using the provided manifests:

```bash
# Apply OpenShift resources
kubectl apply -f openshift/
```

Or use the `mcp_omni_omniroute_*` tools for dynamic configuration adjustments.

## License

Proprietary – Contact Karthago for commercial licensing.
