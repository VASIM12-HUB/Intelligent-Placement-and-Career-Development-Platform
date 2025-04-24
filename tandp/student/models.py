from django.db import models
from tpo.models import *
from django.conf import settings
from decimal import Decimal,ROUND_DOWN
# Create your models here.

class StudentRegistration(models.Model):
    custom_user = models.OneToOneField(
        'tpo.CustomUser', 
        on_delete=models.CASCADE,
        related_name='student_profile',
        null=False,
    )
    rollno = models.CharField(max_length=20, unique=True, primary_key=True)
    full_name = models.CharField(max_length=150)

    def __str__(self):
        return self.rollno


class StudentProfile(models.Model):
    GENDER_CHOICES = [
        ('F', 'Female'),
        ('M', 'Male'),
        ('O', 'Others'),
    ]
    student = models.OneToOneField(StudentRegistration, on_delete=models.CASCADE, primary_key=True)
    college_email = models.EmailField(unique=True) 
    personal_email = models.EmailField(null=True, blank=True) 
    ssc_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    inter_diploma_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    btech_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    department = models.CharField(max_length=100)
    year_of_study = models.IntegerField(null=True, blank=True)
    resume = models.FileField(upload_to="resumes/", null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    profile_picture = models.ImageField(upload_to="profile_pictures/", null=True, blank=True)
    is_placed = models.BooleanField(default=False)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    passed_out_year = models.IntegerField(null=True, blank=True)
    placement_offers = models.ManyToManyField('tpo.Company', through='tpo.PlacementOffer', blank=True)

    @property
    def btech_percent(self):
        """Convert CGPA to percentage using the formula: CGPA * 9.5"""
        if self.btech_cgpa is not None:
            return (self.btech_cgpa * Decimal('9.5')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        return "N/A"
    
    @property
    def academic_year(self):
        if self.passed_out_year:
            return f"{self.passed_out_year - 1}-{self.passed_out_year}"
        return "N/A"

    def __str__(self):
        return f"Profile of {self.student.rollno}"

class StudentTraining(models.Model):
    """Table for training-related data."""
    student = models.OneToOneField(StudentProfile, on_delete=models.CASCADE, primary_key=True)
    training_program = models.CharField(max_length=200, blank=True, null=True)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    score_secured = models.CharField(max_length=20, blank=True, null=True)  
    max_score = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"Training details for {self.student.student.rollno}"