from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("material_service", "0001_initial"), 
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="matchingsubmissionanswer",
            unique_together=None,
        ),

        migrations.DeleteModel(
            name="MatchingSubmissionAnswer",
        ),
        migrations.DeleteModel(
            name="WordOrderSubmissionAnswer",
        ),
        migrations.DeleteModel(
            name="MatchingDistractor",
        ),
        migrations.DeleteModel(
            name="MatchingPair",
        ),
        migrations.DeleteModel(
            name="WordOrderSentence",
        ),
    ]