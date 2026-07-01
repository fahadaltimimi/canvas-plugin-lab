import pytest
from django.db import connection

from lab_order_workflow_example.models.workflow_state import LabOrderWorkflowState


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup: None, django_db_blocker: object) -> None:
    with django_db_blocker.unblock():
        table_names = connection.introspection.table_names()

        if LabOrderWorkflowState._meta.db_table not in table_names:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(LabOrderWorkflowState)
