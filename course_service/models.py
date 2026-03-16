from django.db import models
from auth_service.models import User

class Course(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Черновик'),
        ('published', 'Опубликован'),
        ('free', 'Бесплатно'),
        ('individual', 'Индивидуальный'),
    )
    
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    cover_image = models.ImageField(upload_to='course_covers/', null=True, blank=True)
    created_by = models.ForeignKey(User, related_name='created_courses', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title}"


class CourseTeacher(models.Model):
    course = models.ForeignKey(Course, related_name='teachers', on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, related_name='teaching_courses', on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('course', 'teacher')
    
    def __str__(self):
        return f"{self.teacher.username} - {self.course.title}"


class CourseAssistant(models.Model):
    course = models.ForeignKey(Course, related_name='assistants', on_delete=models.CASCADE)
    assistant = models.ForeignKey(User, related_name='assisting_courses', on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('course', 'assistant')
    
    def __str__(self):
        return f"{self.assistant.username} - {self.course.title}"


class CourseEnrollment(models.Model):
    STATUS_CHOICES = (
        ('active', 'Активен'),
        ('completed', 'Завершен'),
        ('dropped', 'Отчислен'),
    )
    
    course = models.ForeignKey(Course, related_name='enrollments', on_delete=models.CASCADE)
    student = models.ForeignKey(User, related_name='enrolled_courses', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('course', 'student')
    
    def __str__(self):
        return f"{self.student.username} - {self.course.title}"