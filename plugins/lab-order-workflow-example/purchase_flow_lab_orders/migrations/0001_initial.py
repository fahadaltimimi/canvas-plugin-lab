import canvas_sdk.v1.data.base
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="HMACNonceRecord",
            fields=[
                ("dbid", models.BigAutoField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("client_id", models.CharField(max_length=128)),
                ("nonce", models.CharField(max_length=128)),
                ("request_timestamp", models.DateTimeField()),
                ("seen_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "hmacnoncerecord",
            },
            bases=(canvas_sdk.v1.data.base.CustomModel,),
        ),
        migrations.CreateModel(
            name="LabOrderWorkflowState",
            fields=[
                ("dbid", models.BigAutoField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("request_id", models.CharField(max_length=64)),
                ("external_checkout_id", models.CharField(max_length=128)),
                ("canvas_patient_id", models.CharField(max_length=64)),
                ("note_uuid", models.CharField(max_length=64)),
                ("canvas_order_id", models.CharField(blank=True, max_length=64, null=True)),
                ("command_uuid", models.CharField(max_length=64)),
                ("lab_partner", models.CharField(max_length=128)),
                ("test_order_codes", models.JSONField(default=list)),
                ("screening_type", models.CharField(max_length=32)),
                ("test_code", models.CharField(max_length=64)),
                ("requires_manual_review", models.BooleanField(default=False)),
                ("workflow_status", models.CharField(max_length=32)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "laborderworkflowstate",
            },
            bases=(canvas_sdk.v1.data.base.CustomModel,),
        ),
        migrations.AddConstraint(
            model_name="hmacnoncerecord",
            constraint=models.UniqueConstraint(
                fields=("client_id", "nonce"),
                name="uq_hmac_client_nonce",
            ),
        ),
        migrations.AddConstraint(
            model_name="laborderworkflowstate",
            constraint=models.UniqueConstraint(
                fields=("request_id",),
                name="uq_workflow_request_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="laborderworkflowstate",
            constraint=models.UniqueConstraint(
                fields=("canvas_order_id",),
                name="uq_workflow_canvas_order_id",
            ),
        ),
    ]
