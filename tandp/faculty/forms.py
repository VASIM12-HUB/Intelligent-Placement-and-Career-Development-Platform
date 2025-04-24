# faculty/forms.py
from django import forms
from tpo.models import CustomUser
from .models import Faculty

class FacultyRegistrationForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(
        max_length=128, 
        required=False,  # Make password optional
        widget=forms.PasswordInput,
        help_text="Leave blank to keep the existing password."
    )

    class Meta:
        model = Faculty
        fields = ['full_name', 'department', 'phone_number', 'profile_picture']

    def save(self, commit=True):
        faculty = super().save(commit=False)
        custom_user = faculty.custom_user
        custom_user.username = self.cleaned_data['username']
        custom_user.email = self.cleaned_data['email']

        # Only update password if a new one is provided
        if self.cleaned_data['password']:
            custom_user.password = self.cleaned_data['password']  # Plaintext as you requested

        if commit:
            custom_user.save()
            faculty.save()
        return faculty



