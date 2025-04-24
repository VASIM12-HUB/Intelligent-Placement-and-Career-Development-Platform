import logging, openpyxl
from openpyxl import Workbook
from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from faculty.models import *
from faculty.forms import FacultyRegistrationForm
from student.models import *
from student.forms import *
from tpo.models import *

# Logger configuration
logger = logging.getLogger(__name__)

User = get_user_model()  # Since you're using CustomUser instead of default User

def faculty_login(request):
    if request.method == "POST":
        login_input = request.POST.get('login_input')
        password = request.POST.get('password')

        # ✅ First, check for superuser login (with hashed password)
        try:
            if '@' in login_input:
                user = User.objects.get(email=login_input)
            else:
                user = User.objects.get(username=login_input)

            # 🔐 Authenticate superuser using hashed password
            if user.is_superuser and user.check_password(password):
                auth_login(request, user)
                messages.success(request, "Superuser logged in successfully.")
                return redirect('faculty_dashboard')
        except User.DoesNotExist:
            pass  # Continue to faculty authentication if superuser not found

        # 🎓 Faculty authentication (plain text password)
        try:
            if '@' in login_input:
                faculty_member = Faculty.objects.get(custom_user__email=login_input)
            else:
                faculty_member = Faculty.objects.get(custom_user__username=login_input)

            # 🔓 Plain text password check for faculty
            if faculty_member.custom_user.password == password:
                auth_login(request, faculty_member.custom_user)
                messages.success(request, "Faculty logged in successfully.")
                return redirect('faculty_dashboard')
            else:
                messages.error(request, "Invalid password.")
        except Faculty.DoesNotExist:
            messages.error(request, "Invalid username or email.")

        return redirect('faculty_login')

    return render(request, 'login_faculty.html')

def faculty_dashboard(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')

        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        faculty_member = get_object_or_404(Faculty, custom_user=request.user)
        students_in_department = StudentProfile.objects.filter(department=faculty_member.department)

        context = {
            'faculty_member': faculty_member,
            'students_in_department': students_in_department,
        }
        return render(request, 'faculty_dashboard.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in faculty_dashboard: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('faculty_login')

def faculty_logout(request):
    logout(request)
    return redirect('home') 


# View to add a new student
def fac_add_student(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')

        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        # ✅ Consistent form naming (student_form)
        if request.method == 'POST':
            student_form = StudentRegistrationForm(request.POST)
            profile_form = StudentProfileForm(request.POST, request.FILES)

            if student_form.is_valid() and profile_form.is_valid():
                rollno = student_form.cleaned_data['rollno']
                personal_email = profile_form.cleaned_data.get('personal_email')
                college_email = profile_form.cleaned_data.get('college_email')

                # ✅ Duplicate checks
                if get_user_model().objects.filter(username=rollno).exists():
                    messages.error(request, "A user with this roll number already exists.")
                elif get_user_model().objects.filter(email=personal_email).exists():
                    messages.error(request, "A user with this personal email already exists.")
                elif get_user_model().objects.filter(email=college_email).exists():
                    messages.error(request, "A user with this college email already exists.")
                else:
                    with transaction.atomic():
                        user = get_user_model().objects.create(
                            username=rollno,
                            password=student_form.cleaned_data['password'],
                            email=college_email
                        )
                        user.user_type = get_user_model().STUDENT
                        user.save()

                        student_registration = student_form.save(commit=False)
                        student_registration.custom_user = user
                        student_registration.save()

                        student_profile = profile_form.save(commit=False)
                        student_profile.student = student_registration
                        student_profile.save()

                        messages.success(request, "Student added successfully.")
                        return redirect('department_students')
            else:
                messages.error(request, "Please correct the highlighted errors below.")

        else:
            student_form = StudentRegistrationForm()
            profile_form = StudentProfileForm()

        # ✅ Always return forms with user data if invalid
        return render(
            request,
            'fac_add_student.html',
            {'student_form': student_form, 'profile_form': profile_form}
        )

    except Exception as e:
        logger.error(f"Unexpected error in fac_add_student: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return render('department_students')

# View to edit an existing student
def fac_edit_student(request, student_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')

        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        faculty_member = get_object_or_404(Faculty, custom_user=request.user)
        student_profile = get_object_or_404(StudentProfile, pk=student_id)

        if student_profile.department != faculty_member.department:
            return HttpResponseForbidden("You cannot edit this student's profile.")

        if request.method == 'POST':
            student_form = StudentEditForm(request.POST, instance=student_profile.student)
            profile_form = StudentProfileForm(request.POST, request.FILES, instance=student_profile)

            if student_form.is_valid() and profile_form.is_valid():
                student_form.save()
                profile_form.save()
                messages.success(request, "Student profile updated successfully.")
                return redirect('department_students')
            else:
                messages.error(request, "Please correct the errors below.")
        else:
            student_form = StudentEditForm(instance=student_profile.student)
            profile_form = StudentProfileForm(instance=student_profile)

        return render(
            request,
            'fac_edit_student.html',
            {'student_form': student_form, 'profile_form': profile_form}
        )

    except Exception as e:
        logger.error(f"Unexpected error in fac_edit_student (student_id={student_id}): {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('department_students')

# View to delete a student's profile
# Delete Student View
def fac_delete_student(request, student_id):
    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('faculty_login')
    
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden("You are not authorized to view this page.")

    student_profile = get_object_or_404(StudentProfile, pk=student_id)

    if request.method == 'POST':
        try:
            # Get associated StudentRegistration and CustomUser
            student_registration = student_profile.student
            custom_user = getattr(student_registration, 'custom_user', None)

            # Delete StudentProfile
            student_profile.delete()

            # Delete StudentRegistration
            student_registration.delete()

            # Delete CustomUser only if it exists
            if custom_user:
                custom_user.delete()

            messages.success(request, "Student and associated user deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting student: {e}")

        return redirect('department_students')  # Redirect after deletion

    return redirect('department_students')

def department_students(request):
    # Check if user is authenticated
    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('faculty_login')
    
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden("You are not authorized to view this page.")

    # Fetch distinct year_of_study values from the database
    year_of_study_choices = StudentProfile.objects.values_list('year_of_study', flat=True).distinct()

    # Compute distinct academic years (e.g., 2024-2025, 2025-2026, etc.)
    academic_year_choices = set()
    for student in StudentProfile.objects.all():
        if student.passed_out_year:
            academic_year = f"{student.passed_out_year - 1}-{student.passed_out_year}"
            academic_year_choices.add(academic_year)

    # Get faculty member for the department
    faculty_member = get_object_or_404(Faculty, custom_user=request.user)
    
    # Start with all students in the same department as the faculty member
    students_in_department = StudentProfile.objects.filter(department=faculty_member.department)

    # Get filter values from GET request
    gender = request.GET.get('gender')
    ssc_min = request.GET.get('ssc_min')
    ssc_max = request.GET.get('ssc_max')
    inter_min = request.GET.get('inter_min')
    inter_max = request.GET.get('inter_max')
    btech_min = request.GET.get('btech_min')
    btech_max = request.GET.get('btech_max')
    year_of_study = request.GET.get('year_of_study')
    academic_year = request.GET.get('academic_year')

    # Apply filters based on the provided parameters
    if gender:
        students_in_department = students_in_department.filter(gender=gender)
    
    if ssc_min:
        students_in_department = students_in_department.filter(ssc_percentage__gte=ssc_min)
    
    if ssc_max:
        students_in_department = students_in_department.filter(ssc_percentage__lte=ssc_max)
    
    if inter_min:
        students_in_department = students_in_department.filter(inter_diploma_percentage__gte=inter_min)
    
    if inter_max:
        students_in_department = students_in_department.filter(inter_diploma_percentage__lte=inter_max)
    
    if btech_min:
        students_in_department = students_in_department.filter(btech_cgpa__gte=btech_min)
    
    if btech_max:
        students_in_department = students_in_department.filter(btech_cgpa__lte=btech_max)
    
    if year_of_study:
        students_in_department = students_in_department.filter(year_of_study=year_of_study)
    
    if academic_year:
        try:
            # Split the academic year (e.g., '2024-2025') into start and end years
            start_year, end_year = map(int, academic_year.split('-'))
            # Filter students whose passed_out_year matches the end year
            students_in_department = students_in_department.filter(passed_out_year=end_year)
        except ValueError:
            # If there's an invalid academic_year format, skip filtering
            students_in_department = students_in_department.none()

    context = {
        'students_in_department': students_in_department,
        'year_of_study_choices': year_of_study_choices,
        'academic_year_choices': sorted(academic_year_choices),
    }
    
    return render(request, 'department_students.html', context)

def fac_export_to_excel(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')

        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        faculty_member = get_object_or_404(Faculty, custom_user=request.user)

        if request.method == "POST":
            selected_roll_numbers = request.POST.get("selected_students")

            if not selected_roll_numbers:
                messages.warning(request, "No students selected for export.")
                return redirect("placed_students")

            # Validate and clean the roll numbers
            selected_roll_numbers = [roll.strip() for roll in selected_roll_numbers.split(",") if roll.strip()]

            if not selected_roll_numbers:
                messages.error(request, "Invalid roll number selection.")
                return redirect("placed_students")

            # Fetch only selected students belonging to the faculty's department
            students = StudentProfile.objects.filter(
                student__rollno__in=selected_roll_numbers,
                department=faculty_member.department
            )

            if not students.exists():
                messages.error(request, "No matching students found for export.")
                return redirect("placed_students")

            # Create Excel workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Selected Students"

            # Define headers
            headers = ['Roll No', 'Full Name', 'Gender', 'SSC Percentage', 'Inter/Diploma Percentage',
                       'B.Tech CGPA', 'B.Tech Percentage','College Email', 'Personal Email', 'Phone Number', 
                       'Year of Study', 'Passed Out Year']
            ws.append(headers)

            # Populate rows with student data
            for student in students:
                gender_label = dict(StudentProfile.GENDER_CHOICES).get(student.gender, 'Unknown')
                ws.append([
                    student.student.rollno or 'N/A',
                    student.student.full_name or 'N/A',
                    gender_label,
                    student.ssc_percentage or 'N/A',
                    student.inter_diploma_percentage or 'N/A',
                    student.btech_cgpa or 'N/A',
                    student.btech_percent or 'N/A',
                    student.college_email or 'N/A',
                    student.personal_email or 'N/A',
                    student.phone_number or 'N/A',
                    student.year_of_study or 'N/A',
                    student.passed_out_year or 'N/A'
                ])

            # Generate Excel file response
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="selected_students.xlsx"'
            wb.save(response)
            return response

        else:
            return HttpResponseForbidden("Invalid request method.")

    except Exception as e:
        logger.error(f"Unexpected error in fac_export_to_excel: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred during export. Please try again later.")
        return redirect("department_students")


def fac_delete_students(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        if request.method == 'POST':
            selected_rollnos = request.POST.getlist('selected_students')

            if not selected_rollnos:
                messages.error(request, "No students selected for deletion!")
                return redirect('department_students')

            deleted_students = []
            errors = []

            for rollno in selected_rollnos:
                try:
                    # Find student registration, profile, and custom user
                    student_registration = StudentRegistration.objects.filter(rollno=rollno).first()

                    if not student_registration:
                        logger.error(f"Student registration not found for roll number: {rollno}", exc_info=True)
                        errors.append(f"{rollno}: Student registration not found.")
                        continue

                    student_profile = StudentProfile.objects.filter(student=student_registration).first()
                    custom_user = student_registration.custom_user

                    # Delete profile if it exists
                    if student_profile:
                        student_profile.delete()
                    
                    # Delete custom user if it exists
                    if custom_user:
                        custom_user.delete()
                    
                    # Delete student registration
                    student_registration.delete()

                    deleted_students.append(rollno)
                except Exception as e:
                    logger.error(f"Error deleting student {rollno}: {str(e)}", exc_info=True)
                    errors.append(f"{rollno}: {e}")

            if deleted_students:
                messages.success(request, f"Deleted students: {', '.join(deleted_students)}")

            if errors:
                messages.error(request, f"Errors occurred for: {', '.join(errors)}")

            return redirect('department_students')

        return redirect('department_students')
    except Exception as e:
        logger.error(f"Unexpected error in fac_delete_students: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('department_students')


def dept_placed_students(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        faculty_member = get_object_or_404(Faculty, custom_user=request.user)

        # Fetch placed students for the faculty's department
        placed_eligibility = Eligibility.objects.filter(
            application_status="PLACED",
            student__studentprofile__department=faculty_member.department
        ).select_related('student', 'company', 'student__studentprofile')

        placed_students = []
        company_options = set()
        year_options = set()
        academic_year_options = set()  # New academic year filter

        for eligibility in placed_eligibility:
            try:
                company_name = eligibility.company.name if eligibility.company else "N/A"
                student_profile = eligibility.student.studentprofile if eligibility.student else None
                year_of_study = student_profile.year_of_study if student_profile else "N/A"
                academic_year = student_profile.academic_year if student_profile else "N/A"

                # Collect unique companies, years, and academic years
                company_options.add(company_name)
                year_options.add(year_of_study)
                if academic_year != "N/A":
                    academic_year_options.add(academic_year)

                placed_students.append({
                    "rollno": eligibility.student.rollno if eligibility.student else "N/A",
                    "full_name": eligibility.student.full_name if eligibility.student else "N/A",
                    "department": student_profile.department if student_profile else "N/A",
                    "year_of_study": year_of_study,
                    "academic_year": academic_year,
                    "company_name": company_name,
                })
            except Exception as e:
                logger.error(f"Error processing eligibility entry: {str(e)}", exc_info=True)

        # Convert sets to sorted lists
        company_options = sorted(company_options)
        year_options = sorted(year_options)
        academic_year_options = sorted(academic_year_options)

        # Get filter values from request
        selected_company = request.GET.get('company', '')
        selected_year = request.GET.get('year', '')
        selected_academic_year = request.GET.get('academic_year', '')  # New filter

        # Apply filters
        if selected_company:
            placed_students = [s for s in placed_students if s["company_name"] == selected_company]
        if selected_year:
            placed_students = [s for s in placed_students if str(s["year_of_study"]) == selected_year]
        if selected_academic_year:
            placed_students = [s for s in placed_students if s["academic_year"] == selected_academic_year]

        context = {
            'placed_students': placed_students,
            'company_options': company_options,
            'year_options': year_options,
            'academic_year_options': academic_year_options,  # Sending academic year options to template
            'selected_company': selected_company,
            'selected_year': selected_year,
            'selected_academic_year': selected_academic_year,  # Sending selected academic year
        }

        return render(request, 'dept_placed.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in dept_placed_students: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('faculty_login')


def placed_students(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        faculty_member = get_object_or_404(Faculty, custom_user=request.user)

        # Get filter values from request
        selected_company = request.GET.get('company', '')
        selected_branch = request.GET.get('branch', '')
        selected_year = request.GET.get('year', '')
        selected_academic_year = request.GET.get('academic_year', '')

        try:
            # Fetch distinct values for filters
            company_options = Company.objects.values_list('name', flat=True).distinct()
            branch_options = StudentProfile.objects.values_list('department', flat=True).distinct()
            year_options = StudentProfile.objects.values_list('year_of_study', flat=True).distinct()

            # Fetch and format academic years
            academic_year_options = StudentProfile.objects.exclude(passed_out_year__isnull=True).values_list(
                'passed_out_year', flat=True
            ).distinct()
            academic_year_options = sorted([f"{year - 1}-{year}" for year in academic_year_options])
        except Exception as e:
            logger.error(f"Error fetching filter options: {str(e)}", exc_info=True)
            messages.error(request, "Error loading filter options.")
            return redirect('faculty_login')

        try:
            # Query placed students with select_related for optimization
            placed_eligibility = Eligibility.objects.filter(application_status="PLACED").select_related(
                'student', 'company', 'student__studentprofile'
            )

            # Apply filters if selected
            if selected_company:
                placed_eligibility = placed_eligibility.filter(company__name=selected_company)
            if selected_branch:
                placed_eligibility = placed_eligibility.filter(student__studentprofile__department=selected_branch)
            if selected_year:
                placed_eligibility = placed_eligibility.filter(student__studentprofile__year_of_study=selected_year)
            if selected_academic_year:
                academic_start_year = int(selected_academic_year.split("-")[0]) + 1
                placed_eligibility = placed_eligibility.filter(
                    student__studentprofile__passed_out_year=academic_start_year
                )
        except Exception as e:
            logger.error(f"Error querying placed students: {str(e)}", exc_info=True)
            messages.error(request, "Error loading placed students.")
            return redirect('faculty_login')

        # Prepare data for rendering
        placed_students = []
        for eligibility in placed_eligibility:
            try:
                student = eligibility.student
                student_profile = student.studentprofile if student else None
                placed_students.append({
                    "rollno": student.rollno if student else "N/A",
                    "full_name": student.full_name if student else "N/A",
                    "department": student_profile.department if student_profile else "N/A",
                    "year_of_study": student_profile.year_of_study if student_profile else "N/A",
                    "academic_year": student_profile.academic_year if student_profile else "N/A",
                    "company_name": eligibility.company.name if eligibility.company else "N/A",
                })
            except Exception as e:
                logger.error(f"Error processing student data: {str(e)}", exc_info=True)

        context = {
            'placed_students': placed_students,
            'company_options': company_options,
            'branch_options': branch_options,
            'year_options': year_options,
            'academic_year_options': academic_year_options,
            'selected_company': selected_company,
            'selected_branch': selected_branch,
            'selected_year': selected_year,
            'selected_academic_year': selected_academic_year,
        }

        return render(request, 'placed.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in placed_students: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('faculty_login')


def department_faculty(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")

        coordinator = get_object_or_404(Faculty, custom_user=request.user)
        coordinator_department = coordinator.department

        # ✅ Filter faculty members from the same department
        faculty_members = Faculty.objects.filter(
            department=coordinator_department
        ).exclude(custom_user_id__isnull=True)
        
        #for faculty in faculty_members:
        #    print(f"Faculty: {faculty.full_name}, ID: {faculty.custom_user_id}")


        context = {
            'faculty_members': faculty_members,
            'coordinator_department': coordinator_department
        }
        return render(request, 'department_faculty.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in department_faculty: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('faculty_dashboard')


def add_new_faculty(request):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")
        
        if request.method == "POST":
            form = FacultyRegistrationForm(request.POST, request.FILES)
            if form.is_valid():
                username = request.POST.get('username')
                email = request.POST.get('email')

                # ✅ Check if username already exists
                if CustomUser.objects.filter(username=username).exists():
                    messages.error(request, f"Username '{username}' is already taken. Please choose a different one.")
                    return render(request, 'add_new_faculty.html', {'form': form})

                # ✅ Check if email already exists
                if CustomUser.objects.filter(email=email).exists():
                    messages.error(request, f"Email '{email}' is already in use. Please use a different email.")
                    return render(request, 'add_new_faculty.html', {'form': form})

                try:
                    # 1️⃣ Create the CustomUser
                    custom_user = CustomUser.objects.create(
                        username=username,
                        email=email,
                        password=request.POST.get('password'),  # Plaintext password (as requested)
                        is_staff=True
                    )
                    custom_user.user_type = CustomUser.STAFF
                    custom_user.save()

                    # 2️⃣ Create the Faculty and link to CustomUser
                    Faculty.objects.create(
                        custom_user=custom_user,
                        full_name=request.POST.get('full_name'),
                        department=request.POST.get('department'),
                        phone_number=request.POST.get('phone_number'),
                        profile_picture=request.FILES.get('profile_picture')
                    )

                    messages.success(request, "Faculty added successfully with staff privileges.")
                    return redirect('department_faculty')

                except Exception as e:
                    logger.error(f"Unexpected error while creating faculty: {str(e)}", exc_info=True)
                    messages.error(request, "An unexpected error occurred while adding the faculty. Please try again.")
                    return redirect('add_new_faculty')
        else:
            form = FacultyRegistrationForm()

        return render(request, 'add_new_faculty.html', {'form': form})

    except Exception as e:
        logger.error(f"Unexpected error in add_new_faculty: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('department_faculty')

def faculty_edit_view(request, faculty_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')

        # ✅ Ensure only the faculty member or admin/staff can access
        if not (request.user.is_superuser or request.user.is_staff or request.user.id == faculty_id):
            return HttpResponseForbidden("You are not authorized to edit this profile.")

        faculty = get_object_or_404(Faculty, custom_user_id=faculty_id)

        if request.method == "POST":
            form = FacultyRegistrationForm(request.POST, request.FILES, instance=faculty)
            username = request.POST.get('username')
            email = request.POST.get('email')

            # ✅ Check username uniqueness (excluding current user)
            if CustomUser.objects.filter(username=username).exclude(id=faculty.custom_user.id).exists():
                messages.error(request, f"Username '{username}' is already taken. Please choose a different one.")
                return render(request, 'fac_edit.html', {'form': form, 'faculty': faculty})

            # ✅ Check email uniqueness (excluding current user)
            if CustomUser.objects.filter(email=email).exclude(id=faculty.custom_user.id).exists():
                messages.error(request, f"Email '{email}' is already in use. Please use a different email.")
                return render(request, 'fac_edit.html', {'form': form, 'faculty': faculty})

            if form.is_valid():
                try:
                    # ✅ Update CustomUser details
                    faculty.custom_user.username = username
                    faculty.custom_user.email = email
                    faculty.custom_user.save()

                    # ✅ Update Faculty details
                    form.save()

                    messages.success(request, "Your profile has been updated successfully.")
                    return redirect('department_faculty')

                except Exception as e:
                    logger.error(f"Unexpected error while updating faculty details: {str(e)}", exc_info=True)
                    messages.error(request, "An unexpected error occurred while updating your profile.")
                    return render(request, 'fac_edit.html', {'form': form, 'faculty': faculty})

        else:
            # ✅ Pre-fill the form with existing user details
            form = FacultyRegistrationForm(
                instance=faculty,
                initial={
                    'username': faculty.custom_user.username,
                    'email': faculty.custom_user.email,
                }
            )

        return render(request, 'fac_edit.html', {'form': form, 'faculty': faculty})

    except Exception as e:
        logger.error(f"Unexpected error in faculty_edit_view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('department_faculty')


def faculty_delete_view(request, faculty_id):
    try:
        if not request.user.is_authenticated:
            messages.error(request, "You need to log in first.")
            return redirect('faculty_login')
        
        if not (request.user.is_superuser or request.user.is_staff):
            return HttpResponseForbidden("You are not authorized to view this page.")
        
        faculty = get_object_or_404(Faculty, custom_user_id=faculty_id)

        # ✅ Prevent deleting superuser or own account (Optional but recommended)
        if faculty.custom_user.is_superuser:
            messages.error(request, "Cannot delete a superuser account.")
            return redirect('department_faculty')

        if faculty.custom_user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('department_faculty')

        try:
            # ✅ Delete Faculty and linked CustomUser (due to cascading)
            faculty.custom_user.delete()
            messages.success(request, "Faculty deleted successfully.")
            return redirect('department_faculty')

        except Exception as e:
            logger.error(f"Unexpected error while deleting faculty: {str(e)}", exc_info=True)
            messages.error(request, "An unexpected error occurred during deletion.")
            return redirect('department_faculty')

    except Exception as e:
        logger.error(f"Unexpected error in faculty_delete_view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred.")
        return redirect('department_faculty')


@csrf_exempt
def excel(request):
    if not request.user.is_authenticated:
        messages.error(request, "You need to log in first.")
        return redirect('faculty_login')
    
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden("You are not authorized to view this page.")

    if request.method == "POST":
        selected_students = request.POST.get("selected_students", "")
        if not selected_students:
            return HttpResponse("No students selected", status=400)

        roll_numbers = selected_students.split(",")  # Convert to a list

        # Fetch student profiles
        students = get_list_or_404(StudentProfile, student__rollno__in=roll_numbers)

        # Create an Excel workbook and worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Placed Students"

        # Add headers
        headers = ["Roll Number", "Full Name", "Branch", "Year of Study", "Academic Year", "Company Name"]
        ws.append(headers)

        # Write student data
        for student in students:
            # Fetch all companies where the student is placed
            eligibility_records = Eligibility.objects.filter(student=student.student, application_status="PLACED")

            if eligibility_records.exists():
                for eligibility in eligibility_records:
                    ws.append([
                        student.student.rollno,
                        student.student.full_name,
                        student.department,
                        student.year_of_study,
                        student.academic_year,
                        eligibility.company.name,  # Add company name
                    ])
            else:
                # If the student is not placed, still add their entry
                ws.append([
                    student.student.rollno,
                    student.student.full_name,
                    student.department,
                    student.year_of_study,
                    student.academic_year,
                    "N/A",  # No company found
                ])

        # Create response with correct content type for Excel
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="Placed_Students.xlsx"'

        # Save workbook to response
        wb.save(response)

        return response

    return HttpResponse("Invalid request method", status=405)