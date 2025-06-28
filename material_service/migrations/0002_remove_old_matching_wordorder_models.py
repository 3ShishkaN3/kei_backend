# material_service/migrations/0002_remove_old_matching_wordorder_models.py

from django.db import migrations, models # models может не понадобиться, если только удаление

class Migration(migrations.Migration):

    dependencies = [
        ("material_service", "0001_initial"), 
    ]

    operations = [
        # Сначала удаляем зависимости (ForeignKey и unique_together), если они есть,
        # а потом сами модели. Django обычно делает это правильно в DeleteModel.
        # Но если возникают проблемы с ForeignKey constraint, возможно, придется
        # сначала удалять поля ForeignKey из моделей, которые *ссылаются* на удаляемые.
        # Однако, DeleteModel должен сам это обработать.

        # Удаление ForeignKey из MatchingSubmissionAnswer перед удалением MatchingPair (если нужно)
        # Но DeleteModel для MatchingSubmissionAnswer должен сам это сделать.

        migrations.AlterUniqueTogether(
            name="matchingsubmissionanswer", # Старое имя модели
            unique_together=None,
        ),
        # Удаляем поля из MatchingPair, если они не удаляются автоматически с моделью
        # Эти операции могут быть избыточны, если DeleteModel корректно работает.
        # migrations.RemoveField(
        #     model_name="matchingpair", # Старое имя
        #     name="prompt_audio",
        # ),
        # migrations.RemoveField(
        #     model_name="matchingpair",
        #     name="prompt_image",
        # ),
        # migrations.RemoveField(
        #     model_name="matchingpair",
        #     name="test",
        # ),

        # Важно: Порядок удаления моделей. Сначала удаляем те, на которые никто не ссылается,
        # или те, которые являются "дочерними".
        migrations.DeleteModel(
            name="MatchingSubmissionAnswer", # Старое имя
        ),
        migrations.DeleteModel(
            name="WordOrderSubmissionAnswer", # Старое имя
        ),
        migrations.DeleteModel(
            name="MatchingDistractor", # Старое имя
        ),
        migrations.DeleteModel(
            name="MatchingPair", # Старое имя
        ),
        migrations.DeleteModel(
            name="WordOrderSentence", # Старое имя
        ),
        # Если были изменения в Test.TEST_TYPE_CHOICES, которые удаляли старые типы,
        # это должно быть в AlterField операции для модели Test, если Django ее сгенерировал.
        # Если нет, то это изменение только в Python коде и не требует миграции данных.
        # Но если choices влияют на ограничения БД, то AlterField нужен.
        # Пока предполагаем, что изменение choices не требует сложной миграции данных.
    ]