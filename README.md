# AI Universal Memory

This is a Django backend for the AI Universal Memory project, storing user context using Vector Embeddings.

## Setup

1. **Build and Start Key Services**
   ```bash
   docker-compose up --build
   ```

2. **Database Migrations**
   The `pgvector` extension must be enabled in the database before you can use the `VectorField`.
   
   Create a migration to enable the extension:
   
   ```python
   # In a new migration file (e.g., core/migrations/0001_initial.py or a preceding dependency)
   # However, to do it cleanly:
   
   python manage.py makemigrations core --empty --name enable_vector_extension
   ```
   
   Edit the generated migration file:
   
   ```python
   from django.db import migrations
   from pgvector.django import VectorExtension

   class Migration(migrations.Migration):
       dependencies = [
           # ... dependencies ...
       ]

       operations = [
           VectorExtension()
       ]
   ```
   
   Then run normal migrations:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

## API Endpoints

- The server runs on `http://localhost:8000`.
- Use the Django Admin or DRF browsable API to interact.

## Configuration

- Database settings are in `docker-compose.yml`.
- **IMPORTANT**: Change the `DJANGO_SECRET_KEY` in `docker-compose.yml` for production.
