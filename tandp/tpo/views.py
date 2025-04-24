from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout as auth_logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail, EmailMessage
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Count, Avg, Q
from django.conf import settings
from tpo.models import *
from tpo.forms import *
from student.models import *
from student.forms import *
from faculty.models import *
from student.views import search_and_display_images
import logging, json, random, xlwt, pandas as pd, numpy as np, openpyxl
from datetime import datetime
from io import BytesIO
import io
from decimal import Decimal


logger = logging.getLogger(__name__)
User = get_user_model()

def login_tpo(request):
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in.")
        return redirect('tpo_dashboard')

    if request.method == "POST":
        login_input = request.POST['login_input']
        password = request.POST['password']

        admin_user = None
        tpo_user = None

        # Check if Admin User (Django User model)
        if '@' in login_input:
            admin_user = User.objects.filter(email=login_input).first()
            tpo_user = TPO.objects.filter(custom_user__email=login_input).first()
        else:
            admin_user = User.objects.filter(username=login_input).first()
            tpo_user = TPO.objects.filter(custom_user__username=login_input).first()

        # Admin Authentication (hashed password)
        if admin_user:
            admin_user = authenticate(request, username=admin_user.username, password=password)
            if admin_user:
                login(request, admin_user)
                messages.success(request, "Logged in successfully!")
                return redirect('tpo_dashboard')

        # TPO Authentication (plain text password - NOT RECOMMENDED)
        if tpo_user and tpo_user.custom_user.password == password:
            login(request, tpo_user.custom_user)
            messages.success(request, "Logged in successfully!")
            return redirect('tpo_dashboard')

        # If both fail
        messages.error(request, "Invalid login credentials. Please try again.")
        return redirect('login_tpo')

    return render(request, 'login_tpo.html')


def generate_otp():
    return ''.join(random.choices('0123456789', k=6))

def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user_type = None

            # First check for superuser (admin)
            if User.objects.filter(email=email, is_superuser=True).exists():
                user_type = 'admin'
            # Then check for custom user
            elif CustomUser.objects.filter(email=email).exists():
                user_type = 'custom'
            else:
                messages.error(request, "Email not found.")
                return redirect('forgot_password')

            # Generate OTP and store in session
            otp = generate_otp()
            PasswordReset.objects.update_or_create(
                email=email, 
                defaults={'otp': otp}
            )
            
            # Store session data
            request.session['email'] = email
            request.session['otp'] = otp
            request.session['user_type'] = user_type

            send_mail(
                'OTP for Password Reset',
                f'Your OTP is: {otp}',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )

            return redirect('verify_otp')

    else:
        form = ForgotPasswordForm()

    return render(request, 'forgot_password.html', {'form': form})

def reset_password(request):
    if 'OTP_VERIFIED' not in request.session:
        messages.error(request, "Unauthorized access. Please verify OTP first.")
        return redirect('forgot_password')

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            confirm_password = form.cleaned_data['confirm_password']
            
            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return redirect('reset_password')

            email = request.session['email']
            user_type = request.session.get('user_type')

            try:
                if user_type == 'admin':
                    # Explicitly check for superuser again
                    user = User.objects.get(email=email, is_superuser=True)
                    user.set_password(new_password)  # Hashed
                else:
                    user = CustomUser.objects.get(email=email)
                    user.password = new_password  # Plain text

                user.save()

            except (User.DoesNotExist, CustomUser.DoesNotExist):
                messages.error(request, "User not found.")
                return redirect('reset_password')

            # Clear session
            session_keys = ['email', 'otp', 'OTP_VERIFIED', 'user_type']
            for key in session_keys:
                if key in request.session:
                    del request.session[key]

            messages.success(request, "Password reset successfully!")
            return redirect('home')

    else:
        form = ResetPasswordForm()

    return render(request, 'reset_password.html', {'form': form})

def resend_otp(request):
    # Get the email from session (email must have been stored during forgot password step)
    email = request.session.get('email')
    if not email:
        messages.error(request, "No email found. Please start the password reset process.")
        return redirect('forgot_password')

    # Check if email exists in PasswordReset table
    if not PasswordReset.objects.filter(email=email).exists():
        messages.error(request, "Email not found in password reset requests.")
        return redirect('forgot_password')

    # Generate a new OTP
    otp = generate_otp()

    # Update or create the OTP for the email in PasswordReset
    password_reset, created = PasswordReset.objects.update_or_create(
        email=email, 
        defaults={'otp': otp}
    )

    # Send the new OTP to the user's email
    send_mail(
        'OTP for password reset',
        f'Your OTP for password reset is: {otp}',
        settings.EMAIL_HOST_USER,
        [email],
        fail_silently=False,
    )

    # Update the session with the new OTP
    request.session['otp'] = otp

    # Inform the user that the OTP has been resent
    messages.success(request, "A new OTP has been sent to your email.")
    
    return redirect('verify_otp')

def verify_otp(request):
    if request.method == 'POST':
        otp = request.POST['otp']
        if otp == request.session.get('otp'):
            request.session['OTP_VERIFIED'] = True
            messages.success(request, "OTP verified successfully. You can now reset your password.")
            return redirect('reset_password')
        else:
            messages.error(request, "Invalid OTP. Please try again.")

    return render(request,'verify_otp.html')


def dashboard(request):
    students = StudentRegistration.objects.all()
    companies = Company.objects.all()
    placed_students = Eligibility.objects.filter(application_status="PLACED")

    placement_stats = {}
    for entry in placed_students:
        year = entry.company.academic_year
        placement_stats[year] = placement_stats.get(year, 0) + 1

    total_students = students.count()
    total_placements = placed_students.count()
    total_not_placed = total_students - total_placements

    context = {
        'placement_stats': placement_stats,
        'total_students': total_students,
        'total_companies': companies.count(),
        'total_placements': total_placements,
        'total_not_placed': total_not_placed,
    }
    return render(request, 'dashboard.html', context)

def main(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        students = StudentRegistration.objects.all()
        companies = Company.objects.all()
        placed_students = Eligibility.objects.filter(application_status="PLACED")

        placement_stats = {}
        for entry in placed_students:
            year = entry.company.academic_year
            placement_stats[year] = placement_stats.get(year, 0) + 1

        total_students = students.count()
        total_placements = placed_students.count()
        total_not_placed = total_students - total_placements

        context = {
            'placement_stats': placement_stats,
            'total_students': total_students,
            'total_companies': companies.count(),
            'total_placements': total_placements,
            'total_not_placed': total_not_placed,
        }
        return render(request, 'main.html', context)

    except Exception as e:
        logger.error(f"An error occurred in the view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('login_tpo')

# Add Faculty
def add_faculty(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        if request.method == 'POST':
            try:
                # Get form data
                username = request.POST.get('username')
                email = request.POST.get('email')
                password = request.POST.get('password')
                full_name = request.POST.get('full_name')
                department = request.POST.get('department')
                phone_number = request.POST.get('phone_number')
                profile_picture = request.FILES.get('profile_picture')

                # Debugging line
                print(f"Username: {username}, Email: {email}, Full Name: {full_name}")

                # Check if username is already taken
                if get_user_model().objects.filter(username=username).exists():
                    messages.error(request, "Username already taken. Please choose another.")
                    return redirect('add_faculty')

                # Check if email is already taken
                if get_user_model().objects.filter(email=email).exists():
                    messages.error(request, "Email already taken. Please choose another.")
                    return redirect('add_faculty')

                # Create the custom user object without hashing the password
                user = get_user_model().objects.create(
                    username=username,
                    email=email,
                    password=password
                )
                user.is_staff = True  # Make the user a staff member
                user.user_type = get_user_model().STAFF
                user.save()

                # Create the faculty object (faculty table, not user table)
                try:
                    faculty = Faculty.objects.create(
                        custom_user=user,  # Link the custom user to the faculty record
                        full_name=full_name,
                        department=department,
                        phone_number=phone_number,
                        profile_picture=profile_picture
                    )

                    messages.success(request, "Faculty added successfully!")
                    return redirect('view_faculty')  # Redirect to faculty view

                except Exception as e:
                    logger.error(f"Error while creating faculty: {str(e)}", exc_info=True)
                    messages.error(request, f"Error while creating faculty: {e}")
                    return redirect('add_faculty')

            except Exception as e:
                logger.error(f"An unexpected error occurred during faculty creation: {str(e)}", exc_info=True)
                messages.error(request, "An unexpected error occurred while processing the form. Please try again.")
                return redirect('add_faculty')

        # Ensure GET request returns the add faculty form
        return render(request, 'add_faculty.html')

    except Exception as e:
        logger.error(f"An error occurred in add_faculty view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('login_tpo')


# View Faculty
"""def view_faculty(request):
    faculty_list = Faculty.objects.all()
    print(faculty_list)  # Fetch the list of all faculty
    context = {'faculty_list': faculty_list}
    return render(request, 'view_faculty.html', context)"""
def view_faculty(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        try:
            faculty_members = Faculty.objects.all()
            return render(request, 'view_faculty.html', {'faculty_members': faculty_members})

        except Exception as e:
            logger.error(f"Error fetching faculty data: {str(e)}", exc_info=True)
            messages.error(request, "An error occurred while retrieving faculty data. Please try again later.")
            return redirect('login_tpo')

    except Exception as e:
        logger.error(f"An error occurred in view_faculty view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('login_tpo')


# Edit Faculty
def edit_faculty(request, faculty_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        faculty = get_object_or_404(Faculty, pk=faculty_id)

        if request.method == 'POST':
            try:
                # Debug form data
                logger.debug(f"Form Data: full_name={request.POST.get('full_name')}, "
                             f"department={request.POST.get('department')}, phone_number={request.POST.get('phone_number')}")

                # Update Faculty fields
                faculty.full_name = request.POST.get('full_name')
                faculty.department = request.POST.get('department')
                faculty.phone_number = request.POST.get('phone_number')

                # Update profile picture if provided
                if 'profile_picture' in request.FILES:
                    faculty.profile_picture = request.FILES['profile_picture']
                    logger.debug(f"Profile picture updated for {faculty.full_name}")

                # Update password if provided
                password = request.POST.get('password')
                if password:
                    logger.debug(f"Updating password for faculty {faculty.full_name}")
                    faculty.custom_user.password = password  # Direct assignment (as per your setup)
                    faculty.custom_user.save()

                # Update CustomUser fields (email & username)
                faculty.custom_user.email = request.POST.get('email')
                faculty.custom_user.username = request.POST.get('username')
                faculty.custom_user.save()

                # Save Faculty instance
                faculty.save()
                faculty.refresh_from_db()
                logger.debug(f"Updated Faculty: {faculty.full_name}, {faculty.department}, {faculty.phone_number}")

                messages.success(request, "Faculty details updated successfully!")
                return redirect('view_faculty')

            except Exception as e:
                logger.error(f"Error while updating faculty {faculty.full_name}: {str(e)}", exc_info=True)
                messages.error(request, f"An error occurred while updating faculty details: {str(e)}")
                return redirect('edit_faculty', faculty_id=faculty_id)

        # Render the form on GET request
        context = {'faculty': faculty}
        return render(request, 'edit_faculty.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in edit_faculty view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('view_faculty')

# Delete Faculty
def delete_faculty(request, faculty_id):
    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('login_tpo')
    
    is_superuser = request.user.is_superuser
    is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

    if not (is_superuser or is_tpo):
        messages.error(request, "You are not authorized to access this page.")
        return redirect('login_tpo')

    # Try-except for fetching faculty
    try:
        faculty = get_object_or_404(Faculty, pk=faculty_id)
    except Exception as e:
        logger.error(f"Error fetching faculty with ID {faculty_id}: {str(e)}", exc_info=True)
        messages.error(request, f"Faculty with ID {faculty_id} could not be found or an error occurred.")
        return redirect('view_faculty')

    # Try-except for deletion process
    try:
        with transaction.atomic():
            user = faculty.custom_user  # OneToOne relationship with CustomUser
            user.delete()
            faculty.delete()

        messages.success(request, "Faculty user deleted successfully!")

    except Exception as e:
        logger.error(f"Error deleting faculty with ID {faculty_id}: {str(e)}", exc_info=True)
        messages.error(request, f"An error occurred while deleting the faculty: {str(e)}")

    return redirect('view_faculty')

def logout(request):
    auth_logout(request)  # Correct the logout function here
    messages.success(request, "You have been logged out successfully.")
    return redirect('home') 

def add_student(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        if request.method == "POST":
            student_form = StudentRegistrationForm(request.POST)
            profile_form = StudentProfileForm(request.POST, request.FILES)

            if student_form.is_valid() and profile_form.is_valid():
                rollno = student_form.cleaned_data['rollno']
                if StudentRegistration.objects.filter(rollno=rollno).exists():
                    messages.error(request, "Student with this roll number already exists.")
                    return redirect('add_student')

                # Create CustomUser (password stored in plain text as per your setup)
                user = CustomUser.objects.create_user(
                    username=rollno,
                    password=student_form.cleaned_data['password']
                )
                user.user_type = CustomUser.STUDENT
                user.password = student_form.cleaned_data['password']
                user.save()

                # Save StudentRegistration linked to user
                student = student_form.save(commit=False)
                student.custom_user = user
                student.save()

                # Save StudentProfile linked to student
                profile = profile_form.save(commit=False)
                profile.student = student
                profile.save()

                messages.success(request, "Student added successfully!")
                return redirect('view_students')

            else:
                messages.error(request, "Please correct the errors in the form.")

        else:
            # GET request: initialize empty forms
            student_form = StudentRegistrationForm(initial={'rollno': '', 'full_name': '', 'password': ''})
            profile_form = StudentProfileForm(initial={
                'college_email': '', 'personal_email': '', 'ssc_percentage': '', 'inter_diploma_percentage': '',
                'btech_cgpa': '', 'department': '', 'year_of_study': '', 'phone_number': '', 'profile_picture': '',
                'is_placed': False, 'placement_offer_letter': '', 'passed_out_year': '',
            })

        return render(request, 'add_student.html', {
            'student_form': student_form,
            'profile_form': profile_form,
        })

    except Exception as e:
        logger.error(f"An unexpected error occurred while adding student: {str(e)}", exc_info=True)
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('add_student')


# View All Students
def view_students(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        students = StudentRegistration.objects.all()

        if request.method == 'POST':
            gender = request.POST.get('gender')
            ssc_percentage_min = request.POST.get('ssc_percentage_min')
            ssc_percentage_max = request.POST.get('ssc_percentage_max')
            inter_percentage_min = request.POST.get('inter_percentage_min')
            inter_percentage_max = request.POST.get('inter_percentage_max')
            btech_cgpa_min = request.POST.get('btech_cgpa_min')
            btech_cgpa_max = request.POST.get('btech_cgpa_max')
            department = request.POST.get('department')
            year_of_study = request.POST.get('year_of_study')
            academic_year = request.POST.get('academic_year')

            # Apply filters
            if gender:
                students = students.filter(studentprofile__gender=gender)

            if ssc_percentage_min:
                students = students.filter(studentprofile__ssc_percentage__gte=float(ssc_percentage_min))
            if ssc_percentage_max:
                students = students.filter(studentprofile__ssc_percentage__lte=float(ssc_percentage_max))

            if inter_percentage_min:
                students = students.filter(studentprofile__inter_diploma_percentage__gte=float(inter_percentage_min))
            if inter_percentage_max:
                students = students.filter(studentprofile__inter_diploma_percentage__lte=float(inter_percentage_max))

            if btech_cgpa_min:
                students = students.filter(studentprofile__btech_cgpa__gte=float(btech_cgpa_min))
            if btech_cgpa_max:
                students = students.filter(studentprofile__btech_cgpa__lte=float(btech_cgpa_max))

            if department:
                students = students.filter(studentprofile__department=department)

            if year_of_study:
                students = students.filter(studentprofile__year_of_study=year_of_study)

            if academic_year:
                start_year, end_year = academic_year.split('-')
                students = students.filter(studentprofile__passed_out_year=int(end_year))

        # Get unique values for dropdowns
        departments = StudentProfile.objects.values_list('department', flat=True).distinct()
        years = StudentProfile.objects.values_list('year_of_study', flat=True).distinct()

        # Get unique academic years
        academic_years = set(
            f"{profile.passed_out_year - 1}-{profile.passed_out_year}"
            for profile in StudentProfile.objects.exclude(passed_out_year=None)
        )

        context = {
            'students': students,
            'departments': departments,
            'years': years,
            'academic_years': sorted(academic_years),
        }
        return render(request, 'view_students.html', context)

    except Exception as e:
        logger.error(f"An error occurred while viewing students: {str(e)}", exc_info=True)
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('login_tpo')


# Edit Student View
def edit_student(request, student_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        student = get_object_or_404(StudentRegistration, pk=student_id)
        profile = get_object_or_404(StudentProfile, student=student)

        # Check if the user is superuser or staff
        can_edit_rollno = request.user.is_superuser or request.user.is_staff

        if request.method == "POST":
            student_form = StudentEditForm(request.POST, instance=student)
            profile_form = StudentProfileForm(request.POST, request.FILES, instance=profile)

            if student_form.is_valid() and profile_form.is_valid():
                try:
                    # Handle rollno update if allowed
                    if can_edit_rollno:
                        new_rollno = student_form.cleaned_data.get('rollno')
                        if new_rollno and new_rollno != student.rollno:
                            if StudentRegistration.objects.filter(rollno=new_rollno).exclude(pk=student_id).exists():
                                messages.error(request, "Roll number already exists for another student.")
                                return redirect('edit_student', student_id=student_id)
                            student.rollno = new_rollno  # Update the rollno

                    # Handle password update if provided
                    password = student_form.cleaned_data.get('password', None)
                    if password:
                        student.custom_user.password = password  # Directly set password (as per your requirement)

                    # Save both forms
                    student_form.save()  
                    profile_form.save()

                    messages.success(request, "Student details updated successfully!")
                    return redirect('view_students')

                except Exception as form_save_error:
                    logger.error(f"Error saving student details: {str(form_save_error)}", exc_info=True)
                    messages.error(request, f"An error occurred while saving details: {str(form_save_error)}")
            else:
                messages.error(request, "Please correct the errors in the form.")
        
        else:
            student_form = StudentEditForm(instance=student)
            profile_form = StudentProfileForm(instance=profile)

        return render(request, 'edit_student.html', {'student_form': student_form, 'profile_form': profile_form})

    except Exception as e:
        logger.error(f"An error occurred while editing student {student_id}: {str(e)}", exc_info=True)
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('view_students')


# Delete Student View
def delete_student(request, student_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        # Fetch the StudentRegistration object
        student = get_object_or_404(StudentRegistration, pk=student_id)

        try:
            with transaction.atomic():
                # Delete the related StudentProfile
                profile = StudentProfile.objects.get(student=student)
                profile.delete()

                # Delete the associated CustomUser
                user = student.custom_user  # OneToOne relationship with CustomUser
                user.delete()

                # Finally, delete the StudentRegistration record
                student.delete()

            messages.success(request, "Student data deleted successfully!")

        except Exception as deletion_error:
            logger.error(f"Error deleting student {student_id}: {str(deletion_error)}", exc_info=True)
            messages.error(request, f"An error occurred while deleting the student: {str(deletion_error)}")

        return redirect('view_students')

    except Exception as e:
        logger.error(f"Unexpected error during deletion of student {student_id}: {str(e)}", exc_info=True)
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('view_students')

def export_selected_students_to_excel(request):
    try:
        # Authentication and authorization checks remain unchanged
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(
            custom_user=request.user, 
            custom_user__user_type=CustomUser.TPO
        ).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        if request.method == "POST":
            selected_rollnos = request.POST.get("selected_students", "").split(",")

            # Clean empty strings from selected_rollnos
            selected_rollnos = [rn.strip() for rn in selected_rollnos if rn.strip()]

            if not selected_rollnos:
                return HttpResponse("No students selected.", status=400)

            # Get students with their profiles
            students = StudentRegistration.objects.filter(
                rollno__in=selected_rollnos
            ).select_related('studentprofile')

            if not students.exists():
                return HttpResponse("No valid students found.", status=404)

            # Create XLSX response
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="selected_students.xlsx"'

            # Create workbook and worksheet
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Selected Students"

            # Write headers
            headers = [
                "Roll Number", "Full Name",  "Gender", "College Email", "Personal Email",
                "Branch", "SSC Percentage", "Inter/Diploma Percentage", "BTech CGPA", "BTech Percentage",
                "Year of Study", "Passed Out Year", "Phone Number"
            ]
            ws.append(headers)

            # Write student data
            for student in students:
                try:
                    profile = student.studentprofile
                    row = [
                        student.rollno,
                        student.full_name,
                        profile.get_gender_display() if profile.gender else 'N/A',
                        profile.college_email or 'N/A',
                        profile.personal_email or 'N/A',
                        profile.department or 'N/A',
                        profile.ssc_percentage or 0.0,
                        profile.inter_diploma_percentage or 0.0,
                        profile.btech_cgpa if profile.btech_cgpa is not None else 'N/A',
                        profile.btech_percent if profile.btech_cgpa is not None else 'N/A',
                        profile.year_of_study if profile.year_of_study is not None else 'N/A',
                        profile.passed_out_year if profile.passed_out_year is not None else 'N/A',
                        profile.phone_number or 'N/A'
                    ]
                    ws.append(row)
                except Exception as e:
                    logger.error(f"Error processing student {student.rollno}: {str(e)}", exc_info=True)
                    continue  # Skip problematic rows but continue processing

            # Save workbook to response
            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            response.write(buffer.getvalue())
            return response

        else:
            messages.error(request, "Invalid request method.")
            return redirect('view_students')

    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('view_students')

    
def delete_multiple_students(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        if request.method == 'POST':
            selected_rollnos = request.POST.get('selected_students', '').split(',')

            if not selected_rollnos or selected_rollnos == [""]:
                return JsonResponse({'success': False, 'message': 'No students selected for deletion!'})

            success_count = 0
            failure_count = 0
            error_messages = []

            try:
                with transaction.atomic():
                    for rollno in selected_rollnos:
                        try:
                            student = StudentRegistration.objects.get(rollno=rollno)
                            
                            try:
                                profile = StudentProfile.objects.get(student=student)
                                profile.delete()
                            except StudentProfile.DoesNotExist:
                                error_msg = f"Profile for student {rollno} does not exist."
                                logger.error(error_msg, exc_info=True)
                                error_messages.append(error_msg)
                                failure_count += 1
                                continue

                            try:
                                user = student.custom_user
                                user.delete()
                            except AttributeError:
                                error_msg = f"User for student {rollno} does not exist."
                                logger.error(error_msg, exc_info=True)
                                error_messages.append(error_msg)
                                failure_count += 1
                                continue

                            student.delete()
                            success_count += 1

                        except StudentRegistration.DoesNotExist:
                            error_msg = f"Student with roll number {rollno} does not exist."
                            logger.error(error_msg, exc_info=True)
                            error_messages.append(error_msg)
                            failure_count += 1
                        except Exception as e:
                            error_msg = f"Error deleting student {rollno}: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            error_messages.append(error_msg)
                            failure_count += 1

                if success_count > 0:
                    message = f"{success_count} students deleted successfully!"
                    if failure_count > 0:
                        message += f" However, {failure_count} deletions failed."
                    return JsonResponse({'success': True, 'message': message, 'errors': error_messages})

                return JsonResponse({'success': False, 'message': 'No students were deleted.', 'errors': error_messages})

            except Exception as e:
                logger.error(f"Transaction error during multiple deletions: {str(e)}", exc_info=True)
                return JsonResponse({'success': False, 'message': f'An error occurred: {str(e)}'})

        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    except Exception as e:
        logger.error(f"Unexpected error in delete_multiple_students: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'An unexpected error occurred: {str(e)}'})


# Add Company - TPO adds a new company for placement drive
def add_company(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        companies = Company.objects.all()  # Get all companies to display in dropdown
        
        if request.method == 'POST':
            form = CompanyForm(request.POST)
            if form.is_valid():
                try:
                    company_name = form.cleaned_data.get('name')
                    if Company.objects.filter(name__iexact=company_name).exists():
                        messages.error(request, f"Company '{company_name}' already exists.")
                    else:
                        form.save()
                        messages.success(request, 'Company added successfully!')
                        return redirect('add_company')  # Redirect to clear the form
                except Exception as e:
                    logger.error(f"Error saving company: {str(e)}", exc_info=True)
                    messages.error(request, "An error occurred while adding the company.")
            else:
                logger.error(f"Invalid form data: {form.errors.as_json()}", exc_info=True)
                messages.error(request, "Please correct the errors in the form.")
        else:
            form = CompanyForm()
        
        return render(request, 'add_company.html', {
            'form': form,
            'companies': companies
        })
    except Exception as e:
        logger.error(f"Unexpected error in add_company: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('add_company')


def delete_company(request, company_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        # Get the company object to be deleted
        company = get_object_or_404(Company, pk=company_id)
        
        try:
            company_name = company.name
            company.delete()
            messages.success(request, f"'{company_name}' Company has been deleted successfully.")
        except Exception as e:
            logger.error(f"Error deleting company '{company.name}': {str(e)}", exc_info=True)
            messages.error(request, f'Error deleting company: {str(e)}')
        
        return redirect('add_company')  # Redirect to the add company page

    except Exception as e:
        logger.error(f"Unexpected error in delete_company: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('add_company')


# Select Company and Filter Students - TPO can filter students based on various criteria
# View to select a company and filter students

def select_company(request, company_id=None):
    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('login_tpo')
    
    is_superuser = request.user.is_superuser
    is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

    if not (is_superuser or is_tpo):
        messages.error(request, "You are not authorized to access this page.")
        return redirect('login_tpo')
    
    company_id_from_query = request.GET.get('company')
    print("Company ID from query:", company_id_from_query)

    # Fetch company from query or the provided company_id
    if company_id_from_query:
        try:
            company = Company.objects.get(id=company_id_from_query)
            print("Company found:", company.name)
        except Company.DoesNotExist:
            print("Company not found!")
            company = None
    elif company_id:
        company = Company.objects.get(id=company_id)
    else:
        company = None

    students = StudentRegistration.objects.all()

    departments = StudentProfile.objects.values('department').distinct()

    academic_years = set()
    for student_profile in StudentProfile.objects.all():
        if student_profile.passed_out_year:
            academic_years.add(student_profile.passed_out_year - 1) 

    # Handle form submission and filtering
    if request.method == 'POST':
        gender = request.POST.get('gender')
        ssc_percentage_min = request.POST.get('ssc_percentage_min')
        ssc_percentage_max = request.POST.get('ssc_percentage_max')
        inter_percentage_min = request.POST.get('inter_percentage_min')
        inter_percentage_max = request.POST.get('inter_percentage_max')
        btech_cgpa_min = request.POST.get('btech_cgpa_min')
        btech_cgpa_max = request.POST.get('btech_cgpa_max')
        department = request.POST.get('department')
        eligibility_status = request.POST.get('eligibility_status')
        selected_students = request.POST.getlist('selected_students')
        academic_year = request.POST.get('academic_year')
        if academic_year:
            academic_year = int(academic_year)  # Convert to integer
            students = students.filter(studentprofile__passed_out_year=academic_year + 1)

        # Apply filters based on form data
        if gender:
            students = students.filter(studentprofile__gender=gender)
        if ssc_percentage_min:
            students = students.filter(studentprofile__ssc_percentage__gte=ssc_percentage_min)
        if ssc_percentage_max:
            students = students.filter(studentprofile__ssc_percentage__lte=ssc_percentage_max)
        if inter_percentage_min:
            students = students.filter(studentprofile__inter_diploma_percentage__gte=inter_percentage_min)
        if inter_percentage_max:
            students = students.filter(studentprofile__inter_diploma_percentage__lte=inter_percentage_max)
        if btech_cgpa_min:
            students = students.filter(studentprofile__btech_cgpa__gte=btech_cgpa_min)
        if btech_cgpa_max:
            students = students.filter(studentprofile__btech_cgpa__lte=btech_cgpa_max)
        if department:
            students = students.filter(studentprofile__department=department)

        if eligibility_status:
            students = students.filter(eligibility__company=company, eligibility__application_status=eligibility_status)

        print("Number of students after filtering:", students.count())

        # Handle email sending if selected students are provided
        if 'send_email' in request.POST:
            if selected_students:
                selected_students_obj = students.filter(rollno__in=selected_students)
                for student in selected_students_obj:
                    eligibility_obj, created = Eligibility.objects.get_or_create(
                        student=student,
                        company=company,
                        defaults={'is_eligible': True, 'application_status': "ELIGIBLE_NOT_APPLIED"}
                    )
                    if not created:
                        eligibility_obj.application_status = "ELIGIBLE_NOT_APPLIED"
                        eligibility_obj.save()

                # Prepare email data
                subject = request.POST.get('subject')
                message = request.POST.get('message')
                sender_email = 'vijayadurga1649@gmail.com'

                # Handle BCC recipients (split by commas and strip spaces)
                bcc_recipients = request.POST.get('bcc', '').split(',')
                bcc_recipients = [email.strip() for email in bcc_recipients if email.strip()]

                # Debugging: print the BCC list
                print("BCC recipients:", bcc_recipients)

                recipients = [student.studentprofile.personal_email for student in selected_students_obj]
                if recipients:
                    # Create email message
                    if bcc_recipients:
                        email = EmailMessage(
                            subject=subject,
                            body=message,
                            from_email=sender_email,
                            to=recipients,
                            bcc=bcc_recipients,  # BCC recipients added here
                        )
                    else:
                        email = EmailMessage(
                            subject=subject,
                            body=message,
                            from_email=sender_email,
                            to=recipients,
                        )

                    # Handle attachments - get all files from the form
                    attachments = request.FILES.getlist('attachments')

                    # Debugging: print the number of attachments
                    print("Number of attachments:", len(attachments))

                    # Attach each file to the email
                    for file in attachments:
                        email.attach(file.name, file.read(), file.content_type)

                    # Send email
                    email.send(fail_silently=False)

                    # Create notifications
                    for student in selected_students_obj:
                        Notification.objects.create(
                            student=student,
                            company=company,
                            message=f"A mail has been sent with job details. Check for more information."
                        )

                    messages.success(request, 'Emails and notifications sent successfully!')
                else:
                    messages.warning(request, 'No students selected for email.')
            else:
                messages.warning(request, 'No students selected for sending emails.')
    
    status_label_map = dict(Eligibility.STATUS_CHOICES)
    # Fetch eligibility for each student for the selected company **ONLY**
    eligibility_statuses = []
    if company:
        for student in students:
            eligibility_obj = Eligibility.objects.filter(student=student, company=company).first()
            if eligibility_obj:
                readable_status = status_label_map.get(eligibility_obj.application_status, "Not Eligible")
                eligibility_statuses.append((student.rollno, readable_status))
            else:
                eligibility_statuses.append((student.rollno, 'Not Eligible'))  # Default to "Not Eligible"

    return render(request, 'select_company.html', {
        'company': company,
        'students': students,
        'eligibility_statuses': eligibility_statuses,
        'departments': departments,
        'academic_years': academic_years,
    })


# Export students who applied for a particular company to Excel
def export_to_excel(request, company_id):
    try:
        # Authentication check
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        # Authorization check
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(
            custom_user=request.user, 
            custom_user__user_type=CustomUser.TPO
        ).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        # Retrieve company and students with related profiles
        company = get_object_or_404(Company, id=company_id)
        students = StudentRegistration.objects.filter(
            eligibility__company=company,
            eligibility__original_status='ELIGIBLE_APPLIED'
        ).select_related('studentprofile')

        # Prepare Excel response
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{company.name}_applied_students.xlsx"'

        # Create workbook and worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Applied Students'

        # Add headers
        headers = ['Roll Number', 'Full Name', 'College Email', 'Personal Email', 
                 'Branch', '10th Percentage', 'Inter/Diploma Percentage', 'BTech Percentage']
        ws.append(headers)

        # Add data rows
        for student in students:
            try:
                profile = student.studentprofile
                row_data = [
                    student.rollno,
                    student.full_name,
                    profile.college_email or '',
                    profile.personal_email or '',
                    profile.department or '',
                    profile.ssc_percentage or 0.0,
                    profile.inter_diploma_percentage or 0.0,
                    round(float(profile.btech_cgpa) * 9.5, 2) if profile.btech_cgpa else 0.0
                ]
                ws.append(row_data)
            except Exception as e:
                logger.error(f"Error writing data for student {student.rollno}: {str(e)}", exc_info=True)
                continue  # Skip problematic rows

        # Save to response
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response.write(buffer.getvalue())
        return response

    except Exception as e:
        logger.error(f"Failed to export Excel for company ID {company_id}: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred while exporting the data.")
        return redirect('select_company', company_id=company_id)
    
    
# Helper function to clean data (remove spaces and convert to lowercase)   
def clean_data(value):
    if value and pd.notna(value):
        return str(value).strip().replace(" ", "").lower()
    return None

def handle_uploaded_file(f, company):
    error_messages = []  # Collect errors to display in frontend

    try:
        df = pd.read_excel(f)
    except Exception as e:
        error_msg = "Failed to read the uploaded file. Please ensure it's a valid Excel file."
        error_messages.append(error_msg)
        return False, error_messages  # Return errors instead of raising exceptions

    # Clean column names
    df.columns = [col.lower().replace(" ", "_") for col in df.columns]

    required_columns = ['roll_number', 'full_name', 'personal_email', 'branch']
    round_columns = ['round_1', 'round_2', 'round_3', 'round_4', 'round_5', 'round_6']

    # Check if round columns exist and add them to required columns
    existing_round_columns = [col for col in round_columns if col in df.columns]
    required_columns.extend(existing_round_columns)

    # Check for missing mandatory columns
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        error_msg = f"Missing required columns: {', '.join(missing_columns)}. Please upload a valid file."
        error_messages.append(error_msg)
        return False, error_messages  # Return errors

    # Keep only required columns
    df = df[required_columns]
    # Process each row in the dataframe
    for _, row in df.iterrows():
        roll_number = str(row['roll_number']).strip()
        full_name = row['full_name']
        personal_email = row['personal_email']
        branch = row['branch']

        round_data = {round_col: row.get(round_col, '') for round_col in existing_round_columns}

        # Ensure StudentRegistration exists
        try:
            student_registration = StudentRegistration.objects.get(rollno=roll_number)
        except StudentRegistration.DoesNotExist:
            error_msg = f"No StudentRegistration found for roll number: {roll_number}"
            error_messages.append(error_msg)
            continue  # Skip this student

        try:
            # Create or update StudentData
            StudentData.objects.update_or_create(
                student=student_registration,
                company=company,
                defaults={
                    'roll_number': roll_number,
                    'full_name': full_name,
                    'personal_email': personal_email,
                    'branch': branch,
                    **round_data
                }
            )

            # Create or update Eligibility
            Eligibility.objects.update_or_create(
                student=student_registration,
                company=company,
                defaults={'is_eligible': True}
            )

        except Exception as e:
            error_msg = f"Error processing data for roll number {roll_number}: {str(e)}"
            error_messages.append(error_msg)

    return True, error_messages  # Return success and collected errors


def select_company_and_upload(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        companies = Company.objects.all()

        # Handle form submission when a company is selected
        if request.method == 'POST' and 'company' in request.POST:
            company_id = request.POST.get('company')
            company = get_object_or_404(Company, id=company_id)
            request.session['selected_company_id'] = company.id  # Store company in session
            return redirect('upload_student_data')

        return render(request, 'select_company_and_upload.html', {'companies': companies})

    except Exception as e:
        logger.error(f"Unexpected error in select_company_and_upload: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('select_company_and_upload')

"""def upload_student_data(request):
    # Fetch the selected company from the session
    company_id = request.session.get('selected_company_id')
    
    # Check if the company_id exists in the session
    if not company_id:
        messages.error(request, 'No company selected. Please select a company first.')
        return redirect('select_company_and_upload')
    
    # Fetch the company based on the selected ID
    company = get_object_or_404(Company, id=company_id)
    
    # Print statement to check the selected company
    print(f"Selected company: {company.name} (ID: {company.id})")
    
    students = []

    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        handle_uploaded_file(file, company)  # Process the uploaded file for the selected company

        # Fetch updated student data for the selected company directly from the database
        students = StudentData.objects.filter(company=company)  # Fetch updated student data for the company
        
        # Print statement to check how many students were fetched
        print(f"Number of students fetched for company {company.name}: {students.count()}")

        messages.success(request, 'Student data uploaded and processed successfully!')

    # If no file uploaded, directly fetch student data from the database for the selected company
    else:
        students = StudentData.objects.filter(company=company)
        
        # Print statement to check the number of students fetched directly from the database
        print(f"Number of students fetched directly from the database for company {company.name}: {students.count()}")

    # Check if no students are available after filtering
    if not students:
        messages.warning(request, 'No students found for the selected company.')

    return render(request, 'upload_student_data.html', {'students': students, 'company': company})"""

def upload_student_data(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        company_id = request.session.get('selected_company_id')
        if not company_id:
            messages.error(request, 'No company selected. Please select a company first.')
            return redirect('select_company_and_upload')

        company = get_object_or_404(Company, id=company_id)
        students = StudentData.objects.filter(company=company)

        # Handle file upload
        if request.method == 'POST' and request.FILES.get('excel_file'):
            file = request.FILES['excel_file']
            success, errors = handle_uploaded_file(file, company)

            if success:
                students = StudentData.objects.filter(company=company)
                messages.success(request, 'Student data uploaded and processed successfully!')

            # Show all errors in the frontend
            for error in errors:
                messages.error(request, error)

        elif request.method == 'POST':
            messages.error(request, 'No file uploaded. Please select an Excel file.')

        # Handle filters
        round_filter = request.GET.get('round_filter')
        status_filter = request.GET.get('status_filter')
        if round_filter:
            students = students.filter(**{f'{round_filter}__icontains': status_filter})

        return render(request, 'upload_student_data.html', {'students': students, 'company': company})

    except Exception as e:
        logger.error(f"Unexpected error in upload_student_data: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('select_company_and_upload')


def interview_process1(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')

        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        # Read the company data from CSV
        try:
            data = pd.read_csv('csv/company.csv', encoding='latin1')
        except FileNotFoundError as e:
            logger.error(f"CSV file not found: {str(e)}", exc_info=True)
            messages.error(request, "Company data file not found.")
            return redirect('interview_process1')  # Redirect to a safe page

        except Exception as e:
            logger.error(f"Error reading company CSV: {str(e)}", exc_info=True)
            messages.error(request, "An error occurred while loading company data.")
            return redirect('interview_process1')

        company_names = sorted(data['Company'].tolist())

        # Get the selected company from the GET request
        company_name = request.GET.get('company_name', '')

        if company_name:
            try:
                company_info = data[data['Company'] == company_name].iloc[0]
                info = company_info['Info']

                # Collect round details
                rounds = {
                    f'Round {i}': company_info[f'Round {i}']
                    for i in range(1, 7) if pd.notna(company_info[f'Round {i}'])
                }

                # Get images for the selected company
                images = search_and_display_images(company_name, 3)

            except IndexError as e:
                logger.error(f"Company '{company_name}' not found in CSV: {str(e)}", exc_info=True)
                messages.error(request, "Selected company not found in the data.")
                return redirect('interview_process1')

            except Exception as e:
                logger.error(f"Error processing data for '{company_name}': {str(e)}", exc_info=True)
                messages.error(request, "An error occurred while retrieving company details.")
                return redirect('interview_process1')

        else:
            info = ''
            rounds = {}
            images = []

        # Render the template
        return render(request, 'company_info.html', {
            'company_names': company_names,
            'info': info,
            'rounds': rounds,
            'images': images,
            'company_name': company_name,
        })

    except Exception as e:
        logger.error(f"Unexpected error in interview_process1: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('interview_process1')

def adding_company(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        if request.method == 'POST':
            try:
                # Get form data
                company_name = request.POST.get('company_name')
                company_info = request.POST.get('company_info')
                rounds = [request.POST.get(f'round_{i}') for i in range(1, 7)]

                # Validate required fields
                if not company_name or not company_info:
                    messages.error(request, "Company name and information are required.")
                    return redirect('adding_company')

                # Load existing data from CSV
                try:
                    data = pd.read_csv('csv/company.csv', encoding='latin1')
                except FileNotFoundError as e:
                    logger.error(f"Company CSV file not found: {str(e)}", exc_info=True)
                    messages.error(request, "Company data file not found.")
                    return redirect('adding_company')
                except Exception as e:
                    logger.error(f"Error reading company CSV: {str(e)}", exc_info=True)
                    messages.error(request, "An error occurred while loading company data.")
                    return redirect('adding_company')

                # Check if company already exists
                if company_name in data['Company'].values:
                    messages.error(request, "Company already exists.")
                    return redirect('adding_company')

                # Create a new row of data for the new company
                new_row = {
                    'Company': company_name,
                    'Info': company_info,
                    **{f'Round {i}': rounds[i-1] for i in range(1, 7)}
                }

                # Convert the new row into a DataFrame and append
                new_row_df = pd.DataFrame([new_row])
                data = pd.concat([data, new_row_df], ignore_index=True)

                # Save the updated data back to the CSV
                data.to_csv('csv/company.csv', index=False, encoding='latin1')

                messages.success(request, f"Company '{company_name}' added successfully!")
                return redirect('interview_process1')

            except Exception as e:
                logger.error(f"Error while adding company: {str(e)}", exc_info=True)
                messages.error(request, "An error occurred while adding the company.")
                return redirect('adding_company')

        # Pass a list of round numbers to the template
        round_numbers = range(1, 7)
        return render(request, 'adding_company.html', {'round_numbers': round_numbers})

    except Exception as e:
        logger.error(f"Unexpected error in adding_company: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('adding_company')

def edit_company(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        csv_file = 'csv/company.csv'

        # Load CSV data with error handling
        try:
            data = pd.read_csv(csv_file, encoding='latin1')
        except FileNotFoundError as e:
            logger.error(f"Company CSV file not found: {str(e)}", exc_info=True)
            messages.error(request, "Company data file not found.")
            return redirect('edit_company')
        except Exception as e:
            logger.error(f"Error reading company CSV: {str(e)}", exc_info=True)
            messages.error(request, "An error occurred while loading company data.")
            return redirect('edit_company')

        company_names = sorted(data['Company'].tolist())  # Get and sort companies
        selected_company = None
        company_info = ""
        rounds = {f'Round {i}': "" for i in range(1, 7)}  # Initialize rounds

        if request.method == "POST":
            try:
                company_name = request.POST.get("company_name")

                if not company_name:
                    messages.error(request, "Company name is required.")
                    return redirect('edit_company')

                # Find the row index of the selected company
                company_index = data[data["Company"] == company_name].index

                if not company_index.empty:
                    idx = company_index[0]  # Get first matching index
                    
                    # Update company info
                    company_info_post = request.POST.get("company_info")
                    data.at[idx, "Info"] = company_info_post
                    
                    # Update rounds
                    for i in range(1, 7):
                        round_value = request.POST.get(f'round_{i}', "")
                        data.at[idx, f'Round {i}'] = round_value

                    # Save changes back to CSV
                    try:
                        data.to_csv(csv_file, index=False, encoding='latin1')
                    except Exception as e:
                        logger.error(f"Error writing to company CSV: {str(e)}", exc_info=True)
                        messages.error(request, "Failed to save company data.")
                        return redirect('edit_company')

                    messages.success(request, f"Company '{company_name}' updated successfully.")
                    return redirect("interview_process1")
                else:
                    messages.error(request, "Selected company not found.")
                    return redirect('edit_company')

            except Exception as e:
                logger.error(f"Error updating company: {str(e)}", exc_info=True)
                messages.error(request, "An error occurred while updating the company.")
                return redirect('edit_company')

        elif request.method == "GET" and "company_name" in request.GET:
            selected_company = request.GET.get("company_name")
            company_data = data[data["Company"] == selected_company]
            
            if not company_data.empty:
                company_info = company_data.iloc[0]["Info"]
                rounds = {f'Round {i}': company_data.iloc[0].get(f'Round {i}', "") for i in range(1, 7)}
            else:
                messages.error(request, "Selected company not found.")
                return redirect('edit_company')

        return render(request, "edit_company.html", {
            "company_names": company_names,
            "selected_company": selected_company,
            "company_info": company_info,
            "rounds": rounds,
        })

    except Exception as e:
        logger.error(f"Unexpected error in edit_company: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('edit_company')

def view_uploaded_offers(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        companies = Company.objects.all()
        selected_company = None
        placed_students = []

        if request.method == 'POST':
            try:
                company_id = request.POST.get('company_id')
                if company_id:
                    selected_company = get_object_or_404(Company, id=company_id)
                    logger.debug(f"Selected Company: {selected_company}")

                    # Fetch placed students (Eligibility.student is a StudentRegistration instance)
                    placed_students = Eligibility.objects.filter(
                        company=selected_company,
                        application_status="PLACED"
                    ).select_related('student')
                    logger.debug(f"Found {placed_students.count()} placed students.")

                    # Get list of StudentRegistration instances from Eligibility records
                    student_registrations = [eligibility.student for eligibility in placed_students]
                    logger.debug(f"Student Registrations: {[s.rollno for s in student_registrations]}")

                    # Fetch offer letters for the selected company only
                    offer_letters = PlacementOffer.objects.filter(student__student__in=student_registrations, company=selected_company)
                    logger.debug(f"Found {offer_letters.count()} offer letters for {selected_company.name}.")

                    # Map each student's roll number to their specific offer letter file
                    offer_letter_dict = {ol.student.student.rollno: ol.offer_letter for ol in offer_letters}
                    logger.debug(f"Offer Letter Mapping: {offer_letter_dict}")

                    # Attach the file object to each student's instance in placed_students
                    for eligibility in placed_students:
                        rollno = eligibility.student.rollno
                        eligibility.student.offer_letter_url = offer_letter_dict.get(rollno, None)
                        logger.debug(f"Student {rollno} offer letter: {eligibility.student.offer_letter_url}")

            except Exception as e:
                logger.error(f"Error while fetching offer letters: {str(e)}", exc_info=True)
                messages.error(request, "An error occurred while retrieving the offer letters.")
                return redirect('view_uploaded_offers')

        return render(request, 'view_uploaded_offers.html', {
            'companies': companies,
            'selected_company': selected_company,
            'placed_students': placed_students,
        })

    except Exception as e:
        logger.error(f"Unexpected error in view_uploaded_offers: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('view_uploaded_offers')


def send_bulk_notifications(request):
    """Manually trigger email and notification for selected students."""

    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('login_tpo')
    
    is_superuser = request.user.is_superuser
    is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()

    if not (is_superuser or is_tpo):
        messages.error(request, "You are not authorized to access this page.")
        return redirect('login_tpo')
    
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    try:
        data = json.loads(request.body)
        student_ids = data.get("student_ids", [])
        company_id = data.get("company_id")
        current_round = data.get("current_round")  

        if not student_ids or not company_id or not current_round:
            return JsonResponse({"error": "Missing student IDs, company ID, or current round"}, status=400)

        company = get_object_or_404(Company, id=company_id)

        students = StudentData.objects.filter(roll_number__in=student_ids, company=company)

        if not students.exists():
            return JsonResponse({"error": "No students found for the given IDs in this company"}, status=400)

        notifications_sent = 0

        for student in students:
            try:
                student_registration = StudentRegistration.objects.get(rollno=student.roll_number)
            except StudentRegistration.DoesNotExist:
                logger.warning(f"StudentRegistration not found for roll number {student.roll_number}. Skipping...")
                continue  

            round_status = str(getattr(student, current_round, "")).strip().lower()
            
            # Normalize the status by removing spaces
            normalized_status = "".join(round_status.split()).lower()  # Remove spaces and convert to lowercase

            # Fetch or create the Eligibility record
            eligibility, created = Eligibility.objects.get_or_create(student=student_registration, company=company)

            # Handle "qualified" status (processing stage)
            if normalized_status == "qualified":
                message = f"✅ Congratulations! You have been **QUALIFIED** for {company.name} ({current_round.replace('_', ' ').title()})."
                eligibility.application_status = "PROCESSING"

            # Handle "selected" status (placed stage)
            elif normalized_status == "selected":
                message = f"✅ Congratulations! You have been **SELECTED** for {company.name} ({current_round.replace('_', ' ').title()})."
                if eligibility.application_status != "PLACED":
                    eligibility.application_status = "PLACED"
                    company.students_placed += 1  # Increment only if not already placed
                    company.save()

            # If the status is NaN, not qualified, or not selected, mark as REJECTED
            elif normalized_status in ["", "nan", "notqualified", "notselected"]:
                message = f"❌ Unfortunately, you have **not qualified** for {company.name} ({current_round.replace('_', ' ').title()})."
                eligibility.application_status = "REJECTED"
                eligibility.save()  # Set to REJECTED

            # Do not update status if it's None
            else:
                continue

            eligibility.save()  # Save the updated status

            # Create Notification
            Notification.objects.create(student=student_registration, company=company, message=message)

            # Send Email
            try:
                send_mail(
                    subject=f"Application Update - {company.name}",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[student.personal_email],
                    fail_silently=False  
                )
            except Exception as e:
                logger.error(f"Email sending failed for {student.personal_email}: {str(e)}")

            notifications_sent += 1

        return JsonResponse({"message": f"Success: Notifications and Emails sent to {notifications_sent} students."})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)

@csrf_exempt  # Allow form submissions
def update_application_status(request, eligibility_id):
    eligibility = get_object_or_404(Eligibility, id=eligibility_id)

    if request.method == "POST":
        new_status = request.POST.get("status")

        # ✅ Update status only if clicked "ELIGIBLE_APPLIED"
        if new_status == "ELIGIBLE_APPLIED" and eligibility.application_status != "ELIGIBLE_APPLIED":
            eligibility.application_status = "ELIGIBLE_APPLIED"
            eligibility.original_status = "ELIGIBLE_APPLIED"
            eligibility.save()  # 💾 Save the updated record

    return redirect("notifications")



def home(request):
    # Get unique academic years from the database based on passed_out_years
    academic_years = StudentProfile.objects.filter(passed_out_year__isnull=False).values('passed_out_year').distinct()

    # Convert passed_out_years to academic years (e.g., 2024-2025)
    academic_years_list = [
        f"{year['passed_out_year'] - 1}-{year['passed_out_year']}" for year in academic_years
    ]

    # Get the current year
    current_year = datetime.now().year

    # Calculate the current academic year (e.g., 2024-2025 for current year 2025)
    current_academic_year = f"{current_year - 1}-{current_year}"

    # Get the selected academic year from the GET parameters
    selected_year = request.GET.get("academic_year")

    # If no academic year is selected, set the current academic year as the default
    if not selected_year:
        selected_year = current_academic_year

    # Initialize querysets for the filtered data
    placements_filter = Eligibility.objects.all()
    company_filter = Company.objects.all()

    # Split the selected academic year to get the start and end years
    selected_year_start, selected_year_end = map(int, selected_year.split('-'))

    # Get students whose passed_out_year matches the selected academic year
    students_in_year = StudentProfile.objects.filter(
        passed_out_year=selected_year_end
    )


    # If no students are found for the selected year, add a message to context
    if not students_in_year:
        context = {
            "message": f"No data available for the academic year {selected_year}.",
            "academic_years": academic_years_list,
            "selected_year": selected_year,
        }
        return render(request, "home.html", context)

    # Get student roll numbers for the selected academic year
    student_rollnos = [student.student.rollno for student in students_in_year]

    # Filter Eligibility records based on the selected roll numbers
    placements_filter = Eligibility.objects.filter(
        application_status="PLACED",
        student__rollno__in=student_rollnos
    )


    # Filter companies based on the selected academic year
    company_filter = Company.objects.filter(academic_year=selected_year)
    # ✅ Total placements count
    total_placements = placements_filter.count()

    # ✅ Average package (excluding companies with 0 package and ensuring only placed students are considered)
    avg_package = placements_filter.exclude(company__package=0).aggregate(avg=Avg("company__package"))["avg"] or 0

    # ✅ Highest CTC of a placed student
    highest_ctc_data = placements_filter.values("company__name", "company__package").order_by("-company__package").first()
    highest_ctc = highest_ctc_data["company__package"] if highest_ctc_data else 0
    highest_ctc_company = highest_ctc_data["company__name"] if highest_ctc_data else "N/A"

    # ✅ Get total students per department (for selected academic year)
    total_students_per_branch = students_in_year.values("department").annotate(total_students=Count("student"))
    total_students_dict = {entry["department"]: entry["total_students"] for entry in total_students_per_branch}


    # ✅ Get placed students and store unique roll numbers per branch (for selected academic year)
    placed_students_dict = {}
    placed_students = placements_filter.select_related("student__studentprofile")
    for student in placed_students:
        branch = student.student.studentprofile.department
        if branch not in placed_students_dict:
            placed_students_dict[branch] = set()
        placed_students_dict[branch].add(student.student.rollno)

    # Convert sets to lists
    for branch in placed_students_dict:
        placed_students_dict[branch] = list(placed_students_dict[branch])


    # ✅ Merge data to ensure all branches appear
    branch_chart_data = []
    for branch, total_students in total_students_dict.items():
        unique_placed_students = len(placed_students_dict.get(branch, []))  # Corrected to get list
        not_placed_students = total_students - unique_placed_students

        branch_chart_data.append({
            "branch": branch,
            "count": unique_placed_students,  # Unique placed students
            "total_students": total_students,
            "not_placed_students": not_placed_students,  # Include this as a fallback
        })

    # ✅ Company-wise Placements (per academic year)
    company_wise_placements = placements_filter.values("company__name").annotate(count=Count("student")).order_by("-count")
    company_chart_data = [{"company": data["company__name"], "count": data["count"]} for data in company_wise_placements]

    # ✅ Context for template
    context = {
        "total_placements": total_placements,
        "avg_package": round(avg_package, 2),  # Average package of placed students
        "highest_ctc": highest_ctc,
        "highest_ctc_company": highest_ctc_company,
        "branch_chart_data": branch_chart_data,
        "company_chart_data": company_chart_data,  # Company-wise placements data
        "academic_years": academic_years_list,  # Pass the dynamic academic years to the template
        "selected_year": selected_year,  # Pass the selected academic year back to the template
    }

    return render(request, "home.html", context)




def student_tracking(request):
    try:
        # Check if user is authenticated
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
    
        # Check if user is authorized (superuser or TPO)
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()
        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')

        students = StudentProfile.objects.all()
        student_data = []

        # Get filter parameters from GET
        rollno = request.GET.get('rollno')
        branch = request.GET.get('branch')
        year = request.GET.get('year_of_study')
        gender = request.GET.get('gender')
        ssc_min = request.GET.get('ssc_min')
        ssc_max = request.GET.get('ssc_max')
        inter_min = request.GET.get('inter_min')
        inter_max = request.GET.get('inter_max')
        btech_min = request.GET.get('btech_min')
        btech_max = request.GET.get('btech_max')

        # Apply filters
        if rollno:
            students = students.filter(student__rollno__icontains=rollno)
        if branch:
            students = students.filter(department__iexact=branch)
        if year:
            students = students.filter(year_of_study=year)
        if gender:
            students = students.filter(gender=gender)
        if ssc_min:
            students = students.filter(ssc_percentage__gte=float(ssc_min))
        if ssc_max:
            students = students.filter(ssc_percentage__lte=float(ssc_max))
        if inter_min:
            students = students.filter(inter_diploma_percentage__gte=float(inter_min))
        if inter_max:
            students = students.filter(inter_diploma_percentage__lte=float(inter_max))
        if btech_min:
            students = students.filter(btech_cgpa__gte=Decimal(btech_min) / Decimal('9.5'))
        if btech_max:
            students = students.filter(btech_cgpa__lte=Decimal(btech_max) / Decimal('9.5'))
        # Prepare data for the table
        for student in students:
            training = StudentTraining.objects.filter(student=student).first()
            placed = Eligibility.objects.filter(
                student=student.student, 
                application_status="PLACED"
            ).exists()
            placed_companies = Eligibility.objects.filter(
                student=student.student,
                application_status="PLACED"
            ).values_list('company__name', flat=True)
            companies = ", ".join(placed_companies) if placed_companies else "N/A"

            student_data.append({
                'rollno': student.student.rollno,
                'full_name': student.student.full_name,
                'college_email': student.college_email,
                'personal_email': student.personal_email,
                'branch': student.department,
                'ssc_percentage': student.ssc_percentage,
                'inter_diploma_percentage': student.inter_diploma_percentage,
                'btech_percentage': student.btech_percent,
                'training_program': training.training_program if training else "N/A",
                'attendance_percentage': training.attendance_percentage if training else "N/A",
                'score_secured': training.score_secured if training else "N/A",
                'max_score': training.max_score if training else "N/A",
                'placement_status': "Placed" if placed else "Not Placed",
                'company_name': companies,
                'year_of_study': student.year_of_study,
                'gender': student.get_gender_display(),
            })

        context = {
            'student_data': student_data,
            'branches': StudentProfile.objects.values_list('department', flat=True).distinct(),
            'years_of_study': StudentProfile.objects.values_list('year_of_study', flat=True).distinct(),
            'genders': StudentProfile.GENDER_CHOICES,
        }
        return render(request, 'student_tracking.html', context)

    except Exception as e:
        logger.error(f"Error in student_training: {e}", exc_info=True)
        messages.error(request, "An error occurred while processing the student data. Please try again : {e}")
        return redirect('student_tracking')

def training_excel(request):
    try:
        if request.method == 'POST':
            # Authentication Check
            if not request.user.is_authenticated:
                messages.error(request, "You need to log in first.")
                return redirect('login_tpo')
            
            # Authorization Check: Only superusers or TPOs can access this page.
            is_superuser = request.user.is_superuser
            is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()
            if not (is_superuser or is_tpo):
                messages.error(request, "You are not authorized to access this page.")
                return redirect('login_tpo')
            
            # Process selected student IDs from the POST data
            selected = request.POST.get('export_student_ids', '')
            selected_ids = selected.split(',') if selected else []
            
            from .models import StudentProfile, StudentTraining, Eligibility, PlacementOffer
            students = StudentProfile.objects.all()
            if selected_ids:
                students = students.filter(student__rollno__in=selected_ids)
            
            student_data = []
            for student in students:
                training = StudentTraining.objects.filter(student=student).first()
                placed = Eligibility.objects.filter(
                    student=student.student, 
                    application_status="PLACED"
                ).exists()
                offers = PlacementOffer.objects.filter(student=student)
                companies = ", ".join([o.company.name for o in offers]) if offers.exists() else "N/A"
    
                student_data.append({
                    'Roll Number': student.student.rollno,
                    'Full Name': student.student.full_name,
                    'College Email': student.college_email,
                    'Personal Email': student.personal_email,
                    'Branch': student.department,
                    '10th %': student.ssc_percentage,
                    'Inter/Diploma %': student.inter_diploma_percentage,
                    'B.Tech %': student.btech_percent,
                    'Training Program': training.training_program if training else "N/A",
                    'Attendance (%)': training.attendance_percentage if training else "N/A",
                    'Score Secured': training.score_secured if training else "N/A",
                    'Max Score': training.max_score if training else "N/A",
                    'Placement Status': "Placed" if placed else "Not Placed",
                    'Company Name': companies,
                    'Year of Study': student.year_of_study,
                    'Gender': student.get_gender_display(),
                })
    
            # Create an Excel file from the data
            df = pd.DataFrame(student_data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Students')
            output.seek(0)
    
            response = HttpResponse(
                output,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename=exported_students.xlsx'
            return response
        else:
            return HttpResponse("Invalid request", status=400)
    except Exception as e:
        messages.error(request, f"An error occurred while processing your request: {str(e)}")
        return redirect('login_tpo')


def training_upload(request):
    try:
        # Authentication Check
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('login_tpo')
        
        # Authorization Check: Only superusers or TPO users can access this page.
        is_superuser = request.user.is_superuser
        is_tpo = TPO.objects.filter(custom_user=request.user, custom_user__user_type=CustomUser.TPO).exists()
        if not (is_superuser or is_tpo):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('login_tpo')
        
        # Process file upload if POST
        if request.method == 'POST':
            try:
                excel_file = request.FILES['excel_file']
                df = pd.read_excel(excel_file)

                # Check mandatory columns and list missing ones if any
                mandatory_columns = ['Roll Number', 'Full Name', 'Branch']
                missing_columns = [col for col in mandatory_columns if col not in df.columns]
                if missing_columns:
                    messages.error(
                        request,
                        f"Excel file is missing mandatory columns: {', '.join(missing_columns)}"
                    )
                    return redirect('training_upload')

                updated = 0
                errors = []

                for index, row in df.iterrows():
                    try:
                        # Get or create StudentRegistration
                        student_reg, created = StudentRegistration.objects.get_or_create(
                            rollno=row['Roll Number'],
                            defaults={'full_name': row['Full Name']}
                        )

                        # Update or create StudentProfile
                        student_profile, created = StudentProfile.objects.get_or_create(
                            student=student_reg,
                            defaults={'department': row['Branch']}
                        )

                        # Update StudentProfile fields
                        student_profile.department = row['Branch']
                        if 'College Email' in df.columns and pd.notna(row['College Email']):
                            student_profile.college_email = row['College Email']
                        if 'Personal Email' in df.columns and pd.notna(row['Personal Email']):
                            student_profile.personal_email = row['Personal Email']
                        if '10th Percentage' in df.columns and pd.notna(row['10th Percentage']):
                            student_profile.ssc_percentage = row['10th Percentage']
                        if 'Inter/Diploma Percentage' in df.columns and pd.notna(row['Inter/Diploma Percentage']):
                            student_profile.inter_diploma_percentage = row['Inter/Diploma Percentage']
                        if 'B Tech Percentage' in df.columns and pd.notna(row['B Tech Percentage']):
                            # Convert percentage to CGPA assuming formula: CGPA = Percentage / 9.5
                            student_profile.btech_cgpa = row['B Tech Percentage'] / 9.5
                        if 'Year of Study' in df.columns and pd.notna(row['Year of Study']):
                            student_profile.year_of_study = row['Year of Study']
                        if 'Gender' in df.columns and pd.notna(row['Gender']):
                            student_profile.gender = row['Gender']

                        student_profile.save()

                        # Update or create Training Data
                        training_data, created = StudentTraining.objects.get_or_create(
                            student=student_profile
                        )
                        if 'Training Program' in df.columns and pd.notna(row['Training Program']):
                            training_data.training_program = row['Training Program']
                        if 'Attendance(%)' in df.columns and pd.notna(row['Attendance(%)']):
                            training_data.attendance_percentage = row['Attendance(%)']
                        if 'Score Secured' in df.columns and pd.notna(row['Score Secured']):
                            training_data.score_secured = row['Score Secured']
                        if 'Max Score' in df.columns and pd.notna(row['Max Score']):
                            training_data.max_score = row['Max Score']

                        training_data.save()
                        updated += 1

                    except Exception as e:
                        errors.append(f"Row {index + 1}: {str(e)}")
                        continue

                # Provide user feedback
                if errors:
                    messages.error(request, f"{len(errors)} errors occurred during update")
                    for error in errors:
                        messages.warning(request, error)
                if updated:
                    messages.success(request, f"Successfully updated {updated} records")

                return redirect('student_tracking')

            except Exception as e:
                messages.error(request, f"Error processing file: {str(e)}")
                return redirect('training_upload')
        else:
            return render(request, 'training_upload.html')
    
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('login_tpo')
