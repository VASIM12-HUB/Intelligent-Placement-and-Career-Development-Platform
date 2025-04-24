from django.urls import path
from tpo import views


urlpatterns = [
    # TPO Login
    path('login_tpo/', views.login_tpo, name='login_tpo'),
    path('forgot_password/', views.forgot_password, name='forgot_password'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('verify_otp/', views.verify_otp, name='verify_otp'),
    path('resend_otp/', views.resend_otp, name='resend_otp'),
    # TPO Dashboard
    path('tpo_dashboard/', views.main, name='tpo_dashboard'),
    # Add Company
    path('add_company/', views.add_company, name='add_company'),
    path('delete_company/<int:company_id>/', views.delete_company, name='delete_company'),
    path('addfac/', views.add_faculty, name='add_faculty'),  # URL for adding faculty
    path('viewfac/', views.view_faculty, name='view_faculty'),  # URL for viewing faculty
    path('editfac/<int:faculty_id>/', views.edit_faculty, name='edit_faculty'),
    path('deletefac/<int:faculty_id>/', views.delete_faculty, name='delete_faculty'),
    path('logout/', views.logout, name='logout'),
    path('view_students/', views.view_students, name='view_students'),  # View all students
    path('edit_student/<str:student_id>/', views.edit_student, name='edit_student'),
    path('delete_student/<str:student_id>/', views.delete_student, name='delete_student'),  # Delete student
    path('delete_multiple_students/', views.delete_multiple_students, name='delete_multiple_students'),
    path('add_student/', views.add_student, name='add_student'),
    path('select_company/<int:company_id>/', views.select_company, name='select_company'),
    #path('mark_application_status/<int:notification_id>/', views.mark_application_status, name='mark_application_status'),
    path('export_to_excel/<int:company_id>/', views.export_to_excel, name='export_to_excel'),
    path("update-status/<int:eligibility_id>/", views.update_application_status, name="update_application_status"),
    path('upload_company_data/', views.select_company_and_upload, name='select_company_and_upload'),
    path('upload_student_data/', views.upload_student_data, name='upload_student_data'),
    path('send_bulk_notifications/', views.send_bulk_notifications, name='send_bulk_notifications'),
    path('interview_process1/', views.interview_process1, name='interview_process1'),
    path('offer_letters/', views.view_uploaded_offers, name='view_offer_letters'),
    path('adding_company/', views.adding_company, name='adding_company'),
    path("edit_company/", views.edit_company, name="edit_company"),
    path("", views.home, name="home"),
    path('export/', views.export_selected_students_to_excel, name='export_selected_students_to_excel'),

    path('student-tracking/', views.student_tracking, name='student_tracking'),
    path('training-upload/', views.training_upload, name='training_upload'),
    path('training_excel/', views.training_excel, name='training_excel'),
]
