from django.conf import settings
from django.db import models


class ContactDepartment(models.TextChoices):
    SALES = "sales", "Sales"
    SUPPORT = "support", "Support"
    PRESS = "press", "Press"
    PARTNERSHIPS = "partnerships", "Partnerships"


class ContactMessage(models.Model):
    """
    A Support-page or Contact-page submission (spec 6.20; BR business rule:
    "both contact touchpoints should route their submissions to a real
    ticketing/CRM system"). This model *is* that persistent record —
    replacing the prior prototype's no-op toast.
    """

    department = models.CharField(
        max_length=20, choices=ContactDepartment.choices, default=ContactDepartment.SUPPORT
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="contact_messages"
    )
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_department_display()}] {self.name} - {self.subject or self.message[:40]}"
