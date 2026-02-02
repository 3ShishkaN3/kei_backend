from django.apps import AppConfig


class MaterialServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'material_service'
    verbose_name = "Материалы и Тесты"

    def ready(self):
        import material_service.signals
