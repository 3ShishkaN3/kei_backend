import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("material_service", "0002_remove_old_matching_wordorder_models"), 
    ]

    operations = [
        migrations.CreateModel(
            name="DraggableItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=255, verbose_name="Текст на облачке")),
                ("is_distractor", models.BooleanField(default=False, verbose_name="Это лишнее облачко (дистрактор)?")),
                ("test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="draggable_items", to="material_service.test", verbose_name="Тест, к которому относится облачко")),
            ],
            options={"verbose_name": "Перетаскиваемое облачко", "verbose_name_plural": "Перетаскиваемые облачка"},
        ),
        migrations.CreateModel(
            name="MatchTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt_text", models.CharField(blank=True, max_length=500, null=True, verbose_name="Текст-промпт цели")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок отображения цели")),
                ("explanation", models.TextField(blank=True, null=True, verbose_name="Пояснение к этой цели/ответу")),
                ("correct_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="correct_for_targets", to="material_service.draggableitem", verbose_name="Правильное облачко для этой цели")),
                ("prompt_audio", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="match_target_prompts_audio", to="material_service.audiomaterial", verbose_name="Аудио-промпт цели")),
                ("prompt_image", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="match_target_prompts_image", to="material_service.imagematerial", verbose_name="Изображение-промпт цели")),
                ("test", models.ForeignKey(limit_choices_to={"test_type": "drag-to-match"}, on_delete=django.db.models.deletion.CASCADE, related_name="match_targets", to="material_service.test")),
            ],
            options={"verbose_name": "Цель для соотнесения", "verbose_name_plural": "Цели для соотнесения", "ordering": ["test", "order"]},
        ),
        migrations.CreateModel(
            name="DragToMatchSubmissionAnswerItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dropped_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="material_service.draggableitem", verbose_name="Перетащенное облачко")),
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drag_to_match_answers", to="material_service.testsubmission")),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="material_service.matchtarget", verbose_name="Цель (задание)")),
            ],
            options={"verbose_name": "Ответ на соотнесение (одна пара)", "verbose_name_plural": "Ответы на соотнесение (пары)", "unique_together": {("submission", "target")}},
        ),
        migrations.CreateModel(
            name="SentenceOrderSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок слота в предложении")),
                ("correct_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="correct_for_slots", to="material_service.draggableitem", verbose_name="Правильное облачко для этого слота")),
                ("test", models.ForeignKey(limit_choices_to={"test_type": "sentence-order"}, on_delete=django.db.models.deletion.CASCADE, related_name="sentence_order_slots", to="material_service.test")),
            ],
            options={"verbose_name": "Слот для порядка предложений", "verbose_name_plural": "Слоты для порядка предложений", "ordering": ["test", "order"], "unique_together": {("test", "order")}},
        ),
        migrations.CreateModel(
            name="SentenceOrderSubmissionAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("submitted_item_ids_order", models.JSONField(default=list, verbose_name="ID облачков в порядке студента")),
                ("submission", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sentence_order_answer", to="material_service.testsubmission")),
            ],
            options={"verbose_name": "Ответ на порядок предложений", "verbose_name_plural": "Ответы на порядок предложений"},
        ),
    ]