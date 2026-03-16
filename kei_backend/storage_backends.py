from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    location = 'media'
    default_acl = 'private'
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 3600
    addressing_style = 'path'
    
    def __init__(self, *args, **kwargs):
        kwargs['bucket_name'] = settings.AWS_STORAGE_BUCKET_NAME
        kwargs['endpoint_url'] = settings.AWS_S3_ENDPOINT_URL
        kwargs['region_name'] = settings.AWS_S3_REGION_NAME
        super().__init__(*args, **kwargs)


class StaticStorage(S3Boto3Storage):
    """Custom S3 storage for static files"""
    location = 'static'
    default_acl = 'public-read'
    querystring_auth = True
    querystring_expire = 3600
    addressing_style = 'path'
    
    def __init__(self, *args, **kwargs):
        kwargs['bucket_name'] = settings.AWS_STORAGE_BUCKET_NAME
        kwargs['endpoint_url'] = settings.AWS_S3_ENDPOINT_URL
        kwargs['region_name'] = settings.AWS_S3_REGION_NAME
        super().__init__(*args, **kwargs)