import pytest
from django.db import connection

from lab_order_workflow_example.models import HMACNonceRecord, LabOrderWorkflowState


@pytest.fixture(scope="session", autouse=True)
def _ensure_custom_model_tables_for_tests(django_db_setup, django_db_blocker) -> None:
    with django_db_blocker.unblock():
        existing_tables = connection.introspection.table_names()
        with connection.schema_editor() as schema_editor:
            if LabOrderWorkflowState._meta.db_table not in existing_tables:
                schema_editor.create_model(LabOrderWorkflowState)
            if HMACNonceRecord._meta.db_table not in existing_tables:
                schema_editor.create_model(HMACNonceRecord)
