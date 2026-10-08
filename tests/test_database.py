import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgresql_15_or_newer():
    assert connection.vendor == "postgresql"
    # Django 6.1 needs PostgreSQL 15+, pg_version looks like 170011 for 17.11
    assert connection.pg_version >= 150000
