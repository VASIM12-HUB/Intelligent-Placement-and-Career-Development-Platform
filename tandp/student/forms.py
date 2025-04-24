from django import forms
from .models import StudentRegistration, StudentProfile

class StudentRegistrationForm(forms.ModelForm):
    # Password is required during registration
    password = forms.CharField(widget=forms.PasswordInput, required=True)

    class Meta:
        model = StudentRegistration
        fields = ['rollno', 'full_name', 'password']

class StudentEditForm(forms.ModelForm):
    # Password is optional during editing
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = StudentRegistration
        fields = ['rollno', 'full_name', 'password']

    def __init__(self, *args, **kwargs):
        # Allow 'rollno' field to be editable only by superuser or staff
        super().__init__(*args, **kwargs)
        if not kwargs.get('instance') or not kwargs['instance'].custom_user.is_staff:
            self.fields['rollno'].disabled = True  # Disable 'rollno' if not staff/superuser

class StudentProfileForm(forms.ModelForm):
    btech_cgpa = forms.DecimalField(required=False)
    year_of_study = forms.IntegerField(required=False)
    passed_out_year = forms.IntegerField(required=False)
    class Meta:
        model = StudentProfile
        fields = [
            'college_email', 'personal_email', 'ssc_percentage',
            'inter_diploma_percentage', 'btech_cgpa', 'department',
            'year_of_study','gender' , 'resume', 'phone_number', 'profile_picture', 'is_placed','passed_out_year'
        ]

    def save(self, commit=True):
        instance = super().save(commit=False)
        #if instance.passed_out_year:
        #    instance.academic_year = instance.calculate_academic_year()
        if commit:
            instance.save()
        return instance