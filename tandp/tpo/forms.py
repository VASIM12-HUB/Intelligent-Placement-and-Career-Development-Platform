from django import forms
from .models import *
from student.models import *

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'address', 'eligibility_criteria','academic_year', 'job_role', 'package']

class CompanyDetailsForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'address', 'eligibility_criteria', 'academic_year','job_role', 'package']
        widgets = {
            'eligibility_criteria': forms.Textarea(attrs={'rows': 4}),
        }

class StudentFilterForm(forms.Form):
    gender_choices = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Others')
    ]
    
    # Fields for filtering students
    gender = forms.ChoiceField(choices=gender_choices, required=False)
    ssc_percentage = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
    inter_percentage = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
    btech_cgpa = forms.DecimalField(max_digits=4, decimal_places=2, required=False)
    department = forms.CharField(max_length=100, required=False)
    year_of_study = forms.IntegerField(required=False)


class UploadFileForm(forms.Form):
    excel_file = forms.FileField()

class PlacementOfferForm(forms.ModelForm):
    # We use FileField to allow multiple files, but the widget won't use ClearableFileInput
    offer_letter = forms.FileField(required=False)

    class Meta:
        model = PlacementOffer
        fields = ['company', 'offer_letter']


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(widget=forms.TextInput(attrs={
        'class': 'form-control', 
        'placeholder': 'Enter your email'
    }))

class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'New Password'}),
        required=True
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        required=True
    )