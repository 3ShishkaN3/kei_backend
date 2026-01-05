from django.db import migrations, models
from django.db.models import F

def set_order_equal_to_id(apps, _):
    Lesson = apps.get_model('lesson_service', 'Lesson')
    
    Lesson.objects.all().update(order=F('id'))

class Migration(migrations.Migration):

    dependencies = [
        ('course_service', '0005_alter_course_status'),
        ('lesson_service', '0004_alter_sectionitem_content_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='order',
            field=models.PositiveIntegerField(default=0, help_text='Определяет ручной порядок отображения уроков внутри курса', verbose_name='Порядок в курсе'),
        ),

        migrations.RunPython(set_order_equal_to_id),

        migrations.AlterModelOptions(
            name='lesson',
            options={'ordering': ['course', 'order', 'id'], 'verbose_name': 'Урок', 'verbose_name_plural': 'Уроки'},
        ),
        
        migrations.AlterUniqueTogether(
            name='lesson',
            unique_together={('course', 'order')},
        ),
    ]