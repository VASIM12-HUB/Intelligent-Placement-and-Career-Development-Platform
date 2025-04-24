from django.db import models
from student.models import *
from faculty.models import *
from django.contrib.auth.models import AbstractUser
# Create your models here.

class CustomUser(AbstractUser):
    TPO = '1'        # TPO role first
    STAFF = '2'      # Faculty/Staff role second
    STUDENT = '3'    # Student role third

    EMAIL_TO_USER_TYPE_MAP = {
        'tpo': TPO,
        'staff': STAFF,
        'student': STUDENT
    }

    user_type_data = (
        (TPO, "TPO"),
        (STAFF, "Staff/Faculty"),
        (STUDENT, "Student")
    )
    user_type = models.CharField(default=STUDENT, choices=user_type_data, max_length=10)

    # Add related_name to avoid clashes with the default User model
    groups = models.ManyToManyField(
        'auth.Group', 
        related_name='customuser_groups', 
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', 
        related_name='customuser_permissions', 
        blank=True
    )

    def __str__(self):
        return self.username

class TPO(models.Model):
    custom_user = models.OneToOneField(
        'tpo.CustomUser',  
        on_delete=models.CASCADE,
        primary_key=True
    )
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

class Company(models.Model):
    name = models.CharField(max_length=200) 
    address = models.TextField(null=True, blank=True)  
    eligibility_criteria = models.TextField()  
    academic_year = models.CharField(max_length=9)
    job_role = models.CharField(max_length=200)  
    package = models.DecimalField(max_digits=10, decimal_places=2) 
    students_placed = models.IntegerField(default=0)  
    date_added = models.DateTimeField(auto_now_add=True)  

    def __str__(self):
        return f"{self.name} - {self.job_role}"
    

class Notification(models.Model):
    student = models.ForeignKey(StudentRegistration, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    message = models.TextField()
    seen = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Notification for {self.student.rollno} regarding {self.company.name}"
    
class StudentData(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=False)
    student = models.ForeignKey(StudentRegistration, on_delete=models.CASCADE)
    roll_number = models.CharField(max_length=20)
    full_name = models.CharField(max_length=100)
    personal_email = models.EmailField()
    branch = models.CharField(max_length=100)
    round_1 = models.CharField(max_length=100, blank=True, null=True)
    round_2 = models.CharField(max_length=100, blank=True, null=True)
    round_3 = models.CharField(max_length=100, blank=True, null=True)
    round_4 = models.CharField(max_length=100, blank=True, null=True)
    round_5 = models.CharField(max_length=100, blank=True, null=True)
    round_6 = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ('roll_number', 'company')  # Ensure unique combination of roll_number and company

    def __str__(self):
        return f"{self.roll_number} - {self.full_name}"
    
class PlacementOffer(models.Model):
    #student = models.ForeignKey(StudentRegistration, on_delete=models.CASCADE, related_name='placement_offers')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE,null=True, related_name='offer_set')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='placed_students')
    offer_letter = models.FileField(upload_to="offer_letters/")
    date_received = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.rollno} - {self.company.name} Offer"
    

class Eligibility(models.Model):
    STATUS_CHOICES = [
        ("ELIGIBLE_APPLIED", "Eligible and Applied"),
        ("ELIGIBLE_NOT_APPLIED", "Eligible but Not Applied"),
        ("NOT_ELIGIBLE", "Not Eligible"),
        ("PROCESSING", "Processing"),
        ("REJECTED", "Rejected"),
        ("PLACED", "Placed"), 
    ]

    student = models.ForeignKey(StudentRegistration, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    is_eligible = models.BooleanField(default=True)
    eligibility_checked_date = models.DateTimeField(auto_now_add=True)
    
    # To track the original status when the student first applies
    original_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="ELIGIBLE_NOT_APPLIED"
    )

    application_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="NOT_ELIGIBLE"  
    )

    def __str__(self):
        return f"{self.student.rollno} - {self.company.name} - {self.application_status} - {self.original_status}"
    


class PasswordReset(models.Model):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email