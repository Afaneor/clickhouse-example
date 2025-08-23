from django.db import models

# Create your models here.
class ExamplePostgresModel(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Example Model'
        verbose_name_plural = 'Example Models'

    def __str__(self):
        return self.name

