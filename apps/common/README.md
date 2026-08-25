# Common App

This app contains shared/common resources used across the project.

## Models

### UnitOfMeasure
Predefined units for products (e.g., liter, kg, package). Companies pick from this catalog; they cannot create custom units.

### Currency
Predefined currency catalog (ISO 4217 codes like USD, EUR, SYP). Companies select from available currencies.

## Management Commands

### initialize_application
**Primary entry point** for all application initialization tasks. This command orchestrates all setup tasks needed for the application.

**Usage:**
```bash
python manage.py initialize_application
```

This command is automatically run during:
- Docker container startup (docker-compose.yml)
- Production deployment (build.sh)

**What it does:**
1. Calls `seed_common_data` to seed units and currencies
2. (Future) Can call additional initialization commands as needed

**Benefits:**
- Single command to run for complete application setup
- Easy to extend with new initialization tasks
- Clear logging and error handling
- Idempotent - safe to run multiple times

### seed_common_data
Seeds the database with default units of measure and currencies.

**Usage:**
```bash
python manage.py seed_common_data
```

**Note:** Typically called via `initialize_application` rather than directly.

**What it seeds:**
- Units: liter, kg, package
- Currencies: USD, EUR, SYP, GBP, TRY

The command is idempotent - it can be run multiple times safely and will only create missing records.

## Adding New Initialization Tasks

To add a new initialization command:

1. Create your management command in `apps/<your_app>/management/commands/`
2. Add it to the `tasks` list in `initialize_application.py`:

```python
tasks = [
    {
        "name": "Your Task Name",
        "command": "your_command_name",
        "args": [],
        "kwargs": {},
    },
]
```

The task will automatically be included in the initialization process.
