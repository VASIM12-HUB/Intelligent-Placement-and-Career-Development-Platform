from django.urls import path
from student.views import *
from tpo.views import *


urlpatterns = [
    path('register/',register, name='register'),
    path('profile/', profile, name='profile'),
    path('login/', login_view, name='stulogin'),
    path('student_details/', student_details, name='student_details'),
    path('logout/', logout_v, name='stulogout'),
    path('placement/', placement_prediction, name='placement_prediction'),
    path('resume_screening/', resume_screening, name='resume_screening'),
    path('candidate_matching/', candidate_matching, name='candidate_matching'),
    path('interview_process/', interview_process, name='interview_process'),
    path('interview_preparation/', interview_preparation, name='interview_preparation'),
    path('course_recommendations/', course_recommendations, name='course_recommendations'),
    path('notifications/', notifications, name='notifications'),
    path("applied_jobs/", applied_jobs, name="applied_jobs"),
    path('upload_offer_letter/', upload_offer_letter, name='upload_offer_letter'),
]