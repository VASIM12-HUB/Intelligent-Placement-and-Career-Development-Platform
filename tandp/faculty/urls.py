from django.urls import path
from faculty.views import *

urlpatterns = [
    path('faclogin/', faculty_login, name='faculty_login'),
    path('facdashboard/', faculty_dashboard, name='faculty_dashboard'),
    path('logout/', faculty_logout, name='faculty_logout'),
    path('department_students/', department_students, name='department_students'),
    path('add_student/', fac_add_student, name='fac_add_student'),
    path('edit_student/<str:student_id>/', fac_edit_student, name='fac_edit_student'),
    path('delete_student/<str:student_id>/', fac_delete_student, name='fac_delete_student'),
    path('fac_export_to_excel/', fac_export_to_excel, name='fac_export_to_excel'),
    path('delete_students/', fac_delete_students, name='fac_delete_students'),
    path('add/', add_new_faculty, name='add_new_faculty'),
    path('dept_placed_students/',dept_placed_students,name='dept_placed_students'),
    path('department_faculty/', department_faculty, name='department_faculty'),
    path('placed_students/',placed_students,name='placed_students'),
    path('edit_fac/<int:faculty_id>/', faculty_edit_view, name='faculty_edit'),
    path('delete_fac/<int:faculty_id>/', faculty_delete_view, name='faculty_delete'),
    path("excel/", excel, name="excel"),

]