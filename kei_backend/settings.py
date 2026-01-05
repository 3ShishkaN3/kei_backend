import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', cast=bool)




CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# LLM Grading Service
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
LLM_GRADING_MODEL = config('LLM_GRADING_MODEL', default='gemini-2.5-flash-lite')

CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-confirmation-codes': {
        'task': 'auth_service.tasks.cleanup_expired_confirmation_codes',
        'schedule': 300.0,
    },
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    'rest_framework',
    'rest_framework_nested',
    'django_cleanup',
    'drf_yasg',
    'axes',
    'corsheaders',
    
    'auth_service',
    'telegram_service',
    'user_service',
    'course_service',
    'lesson_service',
    'material_service',
    'dict_service',
    'progress_service',
    'calendar_service',
    'achievement_service',
    'bonus_service',
    'storages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]


ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN')
TEACHER_CHAT_ID = config('TEACHER_CHAT_ID')

SWAGGER_SETTINGS = {
    'DEFAULT_AUTO_SCHEMA_CLASS': 'drf_yasg.inspectors.SwaggerAutoSchema',
}

ROOT_URLCONF = 'kei_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'kei_backend.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', cast=int),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]


LANGUAGE_CODE = 'ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'auth_service.User'

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_DOMAIN = "localhost"

SESSION_COOKIE_SECURE = False
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'sessionid'

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5000',
    'https://keisenpai.com',
    'http://100.113.223.9:5000',
    'http://192.168.1.16:5000',
]

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5000',
    'https://keisenpai.com',
    'http://100.113.223.9:5000',
    'http://192.168.1.16:5000',
]


AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'auth_service.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]


AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_USERNAME_CALLABLE = 'auth_service.axes_utils.get_axes_username'

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": "{asctime} {levelname} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file_auth": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/auth_service.log",
            "formatter": "detailed",
        },
        "file_axes": { 
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/axes.log",
            "formatter": "detailed",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed",
        },
    },
    "loggers": {
        "auth_service": {
            "handlers": ["file_auth", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "axes": {
            "handlers": ["file_axes", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "kei_backend.utils": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

if not DEBUG:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        SENTRY_DSN = config('SENTRY_DSN', default='')
        if SENTRY_DSN:
            sentry_sdk.init(
                dsn=SENTRY_DSN,
                integrations=[DjangoIntegration()],
                send_default_pii=True,
                traces_sample_rate=0.0,
            )
    except Exception:
        pass

USE_S3 = config('USE_S3', cast=bool, default=False)

if USE_S3 and not DEBUG:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='ru-central-1')
    
    STORAGES = {
        "default": {
            "BACKEND": "kei_backend.storage_backends.MediaStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_QUERYSTRING_AUTH = True
    

    
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
