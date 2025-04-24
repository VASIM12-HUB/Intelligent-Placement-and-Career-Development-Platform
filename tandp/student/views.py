from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.templatetags.static import static
from django.core.exceptions import ObjectDoesNotExist

# Standard library imports
import io, re, csv, base64, logging, string

# Third-party imports
import pandas as pd, numpy as np, seaborn as sns, matplotlib, torch, gensim, nltk, PyPDF2, pdfplumber, requests, emoji
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from wordcloud import WordCloud
from bs4 import BeautifulSoup
from textblob import TextBlob
from googleapiclient.discovery import build

# App-specific imports
from student.models import *
from student.forms import *
from tpo.models import *
from tpo.views import *
from tpo.forms import PlacementOfferForm 
from student.utils import *
# Matplotlib configuration
matplotlib.use('Agg')
from io import BytesIO

# Configure logger
logger = logging.getLogger(__name__)

# Create your views here.

# Registration View
def register(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            # Get the roll number and password
            username = form.cleaned_data['rollno']  # Assuming rollno is the username
            password = form.cleaned_data['password']  # Plain password from form

            # Create the user (no hashing of password)
            user = get_user_model().objects.create(username=username)
            user.set_password(password)  # Manually set the password, but don't hash it

            # Save the user instance without hashing
            user.password = password  # Assign the plain password directly
            user.save()

            # Now create the student registration, associating the user
            student_registration = form.save(commit=False)
            student_registration.custom_user = user  # Assign the created user
            student_registration.save()

            messages.success(request, 'Registration successful. Please log in to continue.')
            return redirect('stulogin')  # Redirect to the login page

        else:
            print(form.errors)  # Debug: print form errors
            messages.error(request, 'There was an error with your registration.')

    else:
        form = StudentRegistrationForm()

    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        rollno = request.POST['rollno']
        password = request.POST['password']
        
        try:
            # Get the user associated with the roll number
            user_registration = StudentRegistration.objects.get(rollno=rollno)
            user = user_registration.custom_user  # Access the associated user instance

            # Compare password directly (not using hashed password)
            if user.password == password:  # Direct password comparison without hashing
                # Store rollno in session, bypassing Django's user model
                request.session['user_rollno'] = user_registration.rollno

                # Check if the profile is filled
                try:
                    student_profile = user_registration.studentprofile
                    if not all([student_profile.college_email, student_profile.ssc_percentage, student_profile.inter_diploma_percentage]):
                        messages.info(request, 'Please complete your profile before accessing the dashboard.')
                        return redirect('profile')  # Redirect to profile page if profile is incomplete
                except StudentProfile.DoesNotExist:
                    messages.info(request, 'Please complete your profile before accessing the dashboard.')
                    return redirect('profile')

                return redirect('student_details')  # Redirect to the dashboard if profile is complete
            else:
                messages.error(request, 'Invalid password.')
        except StudentRegistration.DoesNotExist:
            messages.error(request, 'Invalid roll number.')

    return render(request, 'login.html')

def student_details(request):
    try:
        # Get rollno from session
        rollno = request.session.get('user_rollno')
        
        # Redirect to login if no rollno in session
        if not rollno:
            messages.error(request, 'You need to log in to access this page.')
            return redirect('stulogin')

        # Fetch the student object
        student = StudentRegistration.objects.get(rollno=rollno)
        
        # Fetch the student profile
        student_profile = student.studentprofile

        # Ensure the profile is complete before showing the student details
        if not all([
            student_profile.college_email,
            student_profile.ssc_percentage,
            student_profile.inter_diploma_percentage
        ]):
            messages.info(request, 'Please complete your profile before accessing the Dashboard.')
            return redirect('profile')  # Redirect to profile if incomplete

        # Render the student details page with the profile details
        return render(request, 'student_details.html', {'profile': student_profile})

    except ObjectDoesNotExist:
        # Handle the case where the student or profile does not exist
        messages.error(request, 'Profile not found. Please contact support.')
        return redirect('profile')

    except Exception as e:
        # Log the error for debugging purposes
        logger.error(f"An error occurred in the student_details view: {str(e)}", exc_info=True)
        
        # Display a user-friendly message
        messages.error(request, 'An unexpected error occurred. Please try again later.')
        return redirect('stulogin')  # Redirect to a safe page (e.g., login)


def profile(request):
    try:
        rollno = request.session.get('user_rollno')
        if not rollno:
            logger.error("No roll number found in session. Redirecting to login.")
            return redirect('stulogin')

        # Fetch student and profile safely
        try:
            student = StudentRegistration.objects.get(rollno=rollno)
            student_profile, created = StudentProfile.objects.get_or_create(student=student)
        except StudentRegistration.DoesNotExist:
            logger.error(f"Student with roll number {rollno} does not exist. Redirecting to login.")
            return redirect('stulogin')

        if request.method == 'POST':
            form = StudentProfileForm(request.POST, request.FILES, instance=student_profile)
            password = request.POST.get('password')

            if form.is_valid():
                old_full_name = student.full_name
                form.save()

                # Update full name if changed
                full_name = form.cleaned_data.get('full_name')
                if full_name and full_name != old_full_name:
                    student.full_name = full_name
                    student.save()

                # Update password if provided and changed
                if password and password != student.custom_user.password:
                    student.custom_user.password = password  
                    student.custom_user.save()

                # Show success message only when actual changes occur
                if form.has_changed() or (password and password != student.custom_user.password):
                    messages.success(request, 'Profile updated successfully!')

                return redirect('student_details')
            else:
                logger.error(f"Form validation failed: {form.errors}")
                messages.error(request, 'There was an error in the form. Please check and submit again.')
        else:
            form = StudentProfileForm(instance=student_profile)

        return render(request, 'profile.html', {
            'form': form,
            'rollno': rollno,
            'full_name': student.full_name,
            'academic_year': student_profile.academic_year,
            'password': student.custom_user.password  # Fetching password from CustomUser
        })

    except Exception as e:
        # Catch-all to prevent Django error pages
        logger.error(f"An unexpected error occurred in profile view: {str(e)}")
        messages.error(request, 'An unexpected error occurred. Please try again later.')
        return redirect('stulogin')
    

def logout_v(request):
    logout(request)
    return redirect('home') 


def placement_prediction(request):
    """Handles student placement prediction with validation rules."""
    try:
        rollno = request.session.get('user_rollno')
        if not rollno:
            logger.error("No roll number found in session. Redirecting to login.")
            return redirect('stulogin')

        context = {}

        # Dropdown mappings
        gender_options = {'Male': 1, 'Female': 0, 'Others': 0}
        boards_ten_options = {'State': 1, 'Central': 0, 'Others': 1}
        boards_twl_options = {'State': 1, 'Central': 0, 'Others': 1}
        twl_stream_options = {'MPC': 2, 'Others': 0}
        work_experience_options = {'Yes': 1, 'No': 0}

        if request.method == 'POST':
            try:
                # Extract inputs safely
                gender = request.POST.get('gender')
                tenth_percentage = float(request.POST.get('tenth_percentage', 0))
                boards_ten = request.POST.get('boards_ten')
                twelfth_percentage = float(request.POST.get('twelfth_percentage', 0))
                boards_twl = request.POST.get('boards_twl')
                twl_stream = request.POST.get('twl_stream')
                ug_percentage = float(request.POST.get('ug_percentage', 0))
                pg_percentage = request.POST.get('pg_percentage', None)
                work_experience = request.POST.get('work_experience')
                skills = request.POST.getlist('skills')

                # Validation checks
                errors = []
                if tenth_percentage < 60:
                    errors.append("10th Percentage must be at least 60%.")
                if twelfth_percentage < 60:
                    errors.append("12th Percentage must be at least 60%.")
                if ug_percentage < 65:
                    errors.append("UG Percentage must be at least 65%.")
                if pg_percentage:
                    try:
                        if float(pg_percentage) < 65:
                            errors.append("PG Percentage must be at least 65% if provided.")
                    except ValueError:
                        logger.error("Invalid PG percentage format.")
                        errors.append("Invalid PG percentage. Please enter a valid number.")
                if not skills:
                    errors.append("Please provide at least one skill.")

                if errors:
                    for error in errors:
                        messages.error(request, error)
                    return render(request, 'placement_prediction.html', context)

                # Prepare model input
                try:
                    df = pd.read_csv('csv/clean_data.csv')
                except FileNotFoundError:
                    logger.error("clean_data.csv file not found.")
                    messages.error(request, "Data file missing. Contact admin.")
                    return render(request, 'placement_prediction.html', context)
                except Exception as e:
                    logger.error(f"Error reading CSV: {str(e)}")
                    messages.error(request, "An unexpected error occurred while reading data.")
                    return render(request, 'placement_prediction.html', context)

                try:
                    model, accuracy = train_model(df)
                except Exception as e:
                    logger.error(f"Model training failed: {str(e)}")
                    messages.error(request, "Model training failed. Please try again later.")
                    return render(request, 'placement_prediction.html', context)

                # Prepare features
                features = [
                    gender_options.get(gender, 0),
                    tenth_percentage,
                    boards_ten_options.get(boards_ten, 0),
                    twelfth_percentage,
                    boards_twl_options.get(boards_twl, 0),
                    twl_stream_options.get(twl_stream, 0),
                    ug_percentage,
                    1,
                    work_experience_options.get(work_experience, 0),
                    0,
                    0,
                    float(pg_percentage) if pg_percentage else 0
                ]

                # Prediction handling
                try:
                    prediction = model.predict([features])[0]
                except Exception as e:
                    logger.error(f"Prediction failed: {str(e)}")
                    messages.error(request, "Prediction failed. Please try again.")
                    return render(request, 'placement_prediction.html', context)

                # Prediction results
                if prediction == 1:
                    context['result'] = "Congratulations! You are eligible for placement."
                    context['improvement'] = None if len(skills) >= 3 else \
                        "However, you need to improve your skills to enhance your chances."
                else:
                    context['result'] = "Sorry! You are not eligible for placement."
                    context['improvement'] = "Consider improving your skills and academic performance."

                context['skills'] = skills if skills else "No Skills Mentioned"
                context['accuracy'] = f"Model Accuracy: {accuracy * 100:.2f}%"

            except (ValueError, KeyError) as e:
                logger.error(f"Invalid data provided: {str(e)}")
                messages.error(request, "Invalid input data. Please check your entries.")
            except Exception as e:
                logger.error(f"Unexpected error during POST processing: {str(e)}")
                messages.error(request, "An unexpected error occurred. Please try again later.")

        return render(request, 'placement_prediction.html', context)

    except Exception as e:
        # Final catch to prevent Django error pages
        logger.error(f"Unexpected error in placement_prediction view: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('stulogin')

def train_model(df):
    # Prepare the data for training
    X = df.iloc[:, :-1].values  # features
    Y = df.iloc[:, -1].values  # target

    X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2)

    # Train the model
    clf = LogisticRegression(random_state=0, solver='lbfgs', max_iter=1000).fit(X_train, Y_train)

    accuracy = clf.score(X_test, Y_test)
    return clf, accuracy

# Generate bar graph from scores
def generate_bar_graph(scored_df):
    try:
        # Ensure column names are correctly set before processing
        if 'Domain/Area' in scored_df.columns:
            scored_df.columns = scored_df.columns.str.replace('Domain/Area', 'Domain_Area')

        # Filter scores greater than 0
        filtered_df = scored_df[scored_df['Score'] > 0]

        # Generate a list of random colors
        colors = plt.cm.get_cmap('tab20', len(filtered_df))  # You can use a different colormap

        fig, ax = plt.subplots()
        ax.bar(filtered_df['Domain_Area'], filtered_df['Score'], color=colors(np.arange(len(filtered_df))))
        ax.set_xlabel('Domain/Area')
        ax.set_ylabel('Score')
        ax.set_title('Score Distribution by Domain/Area')
        plt.xticks(rotation=45, ha='right')

        # Save the plot to a BytesIO object and convert to base64
        buf = BytesIO()
        plt.tight_layout()  # Ensures layout is adjusted correctly
        fig.savefig(buf, format='png')
        buf.seek(0)
        bar_graph_img = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        print("Generated Bar Graph Image Length:", len(bar_graph_img))
        return bar_graph_img
    except Exception as e:
        print("Error generating bar graph:", e)
        return ""


# Generate word cloud from extracted words
def generate_word_cloud(content):
    try:
        wordcloud = WordCloud(width=800, height=400, background_color='white').generate(content)

        # Save the word cloud to a BytesIO object and convert to base64
        buf = BytesIO()
        wordcloud.to_image().save(buf, format='PNG')
        buf.seek(0)
        word_cloud_img = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        print("Generated Word Cloud Image Length:", len(word_cloud_img))
        return word_cloud_img
    except Exception as e:
        print("Error generating word cloud:", e)
        return ""

def resume_screening(request):
    try:
        rollno = request.session.get('user_rollno')  # Get rollno from session

        if not rollno:
            return redirect('stulogin')  # Redirect to login if no rollno in session

        job_recommendation = ''
        word_cloud_img = ''
        bar_graph_img = ''
        scored_df = None

        if request.method == 'POST' and request.FILES.get('resume'):
            uploaded_file = request.FILES['resume']

            try:
                # Extract and preprocess the text directly from the uploaded file
                content = extract_text_from_uploaded_pdf(uploaded_file)
                content = preprocess_text(content)

                # Calculate scores
                scored_df = calculate_scores(content)

                if scored_df is not None and not scored_df.empty:
                    # Generate the bar graph and word cloud images
                    bar_graph_img = generate_bar_graph(scored_df)
                    word_cloud_img = generate_word_cloud(content)

                    # Filter high scores (e.g., scores greater than 1)
                    high_scores_df = scored_df[scored_df['Score'] > 1]

                    # Analyze and recommend
                    total_score = scored_df['Score'].sum()

                    if high_scores_df.empty:
                        job_recommendation = "Resume Does Not Meet The Requirement for any Role."
                    else:
                        # Job recommendation logic with safe access
                        try:
                            def safe_score(domain):
                                return scored_df.loc[scored_df['Domain_Area'] == domain, 'Score'].values[0] \
                                    if domain in scored_df['Domain_Area'].values else 0

                            if total_score >= 50 and safe_score('Data science') >= 2 \
                                    and safe_score('Programming') >= 1 and safe_score('Statistics') >= 1 \
                                    and safe_score('Machine learning') >= 1 and safe_score('Data analytics') >= 1:
                                job_recommendation = "Suggest To Recruit as Data Scientist."

                            elif total_score >= 50 and safe_score('Sales & marketing') >= 2 \
                                    and safe_score('Personal Skill') >= 1 and safe_score('Management skill') >= 1 \
                                    and safe_score('Experience') >= 1:
                                job_recommendation = "Suggest To Recruit as Account Executive."

                            elif total_score >= 50 and safe_score('Content skill') >= 2 \
                                    and safe_score('Graphic') >= 1 and safe_score('Personal Skill') >= 1:
                                job_recommendation = "Suggest To Recruit as Content Creator."

                            elif total_score >= 50 and safe_score('Data analytics') >= 2 \
                                    and safe_score('Statistics') >= 1 and safe_score('Data analyst') >= 1 \
                                    and safe_score('Data science') >= 1:
                                job_recommendation = "Suggest To Recruit as Data Analyst."

                            elif total_score >= 50 and safe_score('Sales & marketing') >= 2 \
                                    and safe_score('Accounting') >= 1 and safe_score('Management skill') >= 1:
                                job_recommendation = "Suggest To Recruit as Sales Executive."

                            elif total_score >= 50 and safe_score('Programming') >= 2 \
                                    and safe_score('Software') >= 1 and safe_score('Experience') >= 1:
                                job_recommendation = "Suggest To Recruit as Software Engineer."

                            elif total_score >= 50 and safe_score('Web skill') >= 2 \
                                    and safe_score('Graphic') >= 1 and safe_score('Personal Skill') >= 1:
                                job_recommendation = "Suggest To Recruit as Web and Graphic Designer."
                            else:
                                job_recommendation = "Resume Does Not Meet The Requirement for any Role."

                        except Exception as e:
                            logger.error(f"Error in recommendation logic for Roll No {rollno}: {str(e)}")
                            job_recommendation = "Error in analyzing resume. Please try again later."

                else:
                    job_recommendation = "Resume Does Not Meet The Requirement for any Role."

            except Exception as e:
                logger.error(f"Error processing resume for Roll No {rollno}: {str(e)}")
                return JsonResponse({'error': 'An error occurred while processing the resume.'}, status=500)

        # Ensure to replace column names safely if needed
        if scored_df is not None:
            try:
                scored_df.columns = scored_df.columns.str.replace('Domain/Area', 'Domain_Area')
            except Exception as e:
                logger.error(f"Error renaming columns: {str(e)}")

        scored_data = scored_df.to_dict(orient='records') if scored_df is not None else []

        return render(request, 'resume_screening.html', {
            'scored_df': scored_data,
            'job_recommendation': job_recommendation,
            'bar_graph_img': bar_graph_img,
            'word_cloud_img': word_cloud_img,
        })

    except Exception as e:
        logger.error(f"Unexpected error in resume_screening: {str(e)}")
        return JsonResponse({'error': 'An unexpected error occurred. Please contact support.'}, status=500)


# Function to extract text directly from the uploaded PDF
def extract_text_from_uploaded_pdf(uploaded_file):
    reader = PyPDF2.PdfReader(uploaded_file)
    content = ""
    for page in reader.pages:
        text= page.extract_text() or ""  # Handle None values safely
        content+=text
    return content


# Preprocessing function
def preprocess_text(content):
    content = content.lower()
    content = re.sub(r'\d+', '', content)  # Remove numbers
    content = content.translate(str.maketrans('', '', string.punctuation))  # Remove punctuation
    content = ' '.join(content.split())  # Remove extra spaces
    return content

def calculate_scores(content):
    Area_with_key_term = {
        'Data science': ['algorithm', 'analytics', 'hadoop', 'machine learning', 'data mining', 'python',
                        'statistics', 'data', 'statistical analysis', 'data wrangling', 'algebra', 'Probability',
                        'visualization'],
        'Programming': ['python', 'r programming', 'sql', 'c++', 'scala', 'julia', 'tableau', 'javascript',
                        'powerbi', 'code', 'coding'],
        'Experience': ['project', 'years', 'company', 'excellency', 'promotion', 'award', 'outsourcing', 'work in progress'],
        'Management skill': ['administration', 'budget', 'cost', 'direction', 'feasibility analysis', 'finance', 
                            'leader', 'leadership', 'management', 'milestones', 'planning', 'problem', 'project', 
                            'risk', 'schedule', 'stakeholders', 'English'],
        'Data analytics': ['api', 'big data', 'clustering', 'code', 'coding', 'data', 'database', 'data mining', 
                        'data science', 'deep learning', 'hadoop', 'hypothesis test', 'machine learning', 'dbms', 
                        'modeling', 'nlp', 'predictive', 'text mining', 'visualization'],
        'Statistics': ['parameter', 'variable', 'ordinal', 'ratio', 'nominal', 'interval', 'descriptive', 
                        'inferential', 'linear', 'correlations', 'probability', 'regression', 'mean', 'variance', 
                        'standard deviation'],
        'Machine learning': ['supervised learning', 'unsupervised learning', 'ann', 'artificial neural network', 
                            'overfitting', 'computer vision', 'natural language processing', 'database'],
        'Data analyst': ['data collection', 'data cleaning', 'data processing', 'interpreting data', 
                        'streamlining data', 'visualizing data', 'statistics', 'tableau', 'tables', 'analytical'],
        'Software': ['django', 'cloud', 'gcp', 'aws', 'javascript', 'react', 'redux', 'es6', 'node.js', 
                    'typescript', 'html', 'css', 'ui', 'ci/cd', 'cashflow'],
        'Web skill': ['web design', 'branding', 'graphic design', 'seo', 'marketing', 'logo design', 'video editing', 
                    'es6', 'node.js', 'typescript', 'html/css', 'ci/cd'],
        'Personal Skill': ['leadership', 'team work', 'integrity', 'public speaking', 'team leadership', 
                            'problem solving', 'loyalty', 'quality', 'performance improvement', 'six sigma', 
                            'quality circles', 'quality tools', 'process improvement', 'capability analysis', 
                            'control'],
        'Accounting': ['communication', 'sales', 'sales process', 'solution selling', 'crm', 'sales management', 
                    'sales operations', 'marketing', 'direct sales', 'trends', 'b2b', 'marketing strategy', 
                    'saas', 'business development'],
        'Sales & marketing': ['retail', 'manufacture', 'corporate', 'goods sale', 'consumer', 'package', 'fmcg', 
                            'account', 'management', 'lead generation', 'cold calling', 'customer service', 
                            'inside sales', 'sales', 'promotion'],
        'Graphic': ['brand identity', 'editorial design', 'design', 'branding', 'logo design', 'letterhead design', 
                    'business card design', 'brand strategy', 'stationery design', 'graphic design', 'exhibition graphic design'],
        'Content skill': ['editing', 'creativity', 'content idea', 'problem solving', 'writer', 'content thinker', 
                        'copy editor', 'researchers', 'technology geek', 'public speaking', 'online marketing'],
        'Graphical content': ['photographer', 'videographer', 'graphic artist', 'copywriter', 'search engine optimization', 
                            'seo', 'social media', 'page insight', 'gain audience'],
        'Finanace': ['financial reporting', 'budgeting', 'forecasting', 'strong analytical thinking', 'financial planning', 
                    'payroll tax', 'accounting', 'productivity', 'reporting costs', 'balance sheet', 'financial statements'],
        'Health/Medical': ['abdominal surgery', 'laparoscopy', 'trauma surgery', 'adult intensive care', 'pain management', 
                        'cardiology', 'patient', 'surgery', 'hospital', 'healthcare', 'doctor', 'medicine'],
        'Language': ['english', 'malay', 'mandarin', 'bangla', 'hindi', 'tamil']
    }

    scores = {domain: sum(1 for word in terms if word in content) for domain, terms in Area_with_key_term.items()}

    # Convert to DataFrame
    scored_df = pd.DataFrame(list(scores.items()), columns=['Domain/Area', 'Score']).sort_values(by='Score', ascending=False)

    return scored_df

"""def candidate_matching(request):
    rollno = request.session.get('user_rollno')  # Get rollno from session
    
    if not rollno:
        return redirect('stulogin')  # Redirect to login if no rollno in session

    skills = []
    score = None
    result_message = ''
    result_image = ''

    if request.method == 'POST':
        jd_text = request.POST.get('jd_text', '').strip()
        uploaded_files = request.FILES.getlist('resume')

        if not jd_text or len(jd_text.split()) < 2:
            result_message = "Please provide a more detailed job description."
            result_image = static("images/error.png")  # Error image
            skills = [("Consider enhancing your resume with relevant skills.", static("images/Improve.png"))]  # Using static path for 'Improve' image
            return render(request, 'candidate_matching.html', {
                'result_message': result_message,
                'result_image': result_image,
                'skills': skills,
                'score': score,
            })

        if uploaded_files:
            uploaded_file_paths = [extract_text_from_uploaded_pdf(file) for file in uploaded_files]
            score = compare(uploaded_file_paths, jd_text, flag='HuggingFace-BERT')

            my_dict = {uploaded_files[i].name: score[i] for i in range(len(score))}
            sorted_dict = dict(sorted(my_dict.items()))
            ct_items = list(sorted_dict.items())
            score = ct_items[0][1]  # Get the score of the first file
            sc = float(score)

            if sc >= 75:
                result_message = "The Candidate is a good match for the Job."
                result_image = "https://media.istockphoto.com/id/1385218939/vector/people-crowd-applause-hands-clapping-business-teamwork-cheering-ovation-delight-vector.jpg?s=612x612&w=0&k=20&c=7NMaUB4zGoXoePxiy-XxKap53GMBQvmIYOSW1tVSFMY="
            elif sc >= 50:
                result_message = "The Candidate is a moderate match for the Job."
                result_image = static("images/moderate.png")  # Moderate match image using static path

            else:
                result_message = "The Candidate is not a good match for the Job."
                result_image = static("images/bad.png")  # Bad match image using static path

            # Always display skills to improve
            JD = preprocess_text(jd_text)
            scored_df = calculate_scores(JD)
            high_scores_df = scored_df[scored_df['Score'] > 1]

            if not high_scores_df.empty:
                data = pd.read_csv('csv/image.csv')  # Load the CSV with skills and images
                skills = []
                for _, row in high_scores_df.iterrows():
                    skill_name = row['Domain/Area']
                    img = data[data['Skill'] == str(skill_name)]['Image'].values[0]
                    skills.append((skill_name, img))
            else:
                skills = [("Consider enhancing your resume with relevant skills.", static("images/Improve.png"))]  # Static path for 'Improve' image

    return render(request, 'candidate_matching.html', {
        'result_message': result_message,
        'result_image': result_image,
        'skills': skills,
        'score': score,
    })"""

def candidate_matching(request):
    try:
        rollno = request.session.get('user_rollno')  # Get rollno from session
        if not rollno:
            return redirect('stulogin')  # Redirect to login if no rollno in session

        skills = []
        score = None
        result_message = ''
        result_image = ''

        if request.method == 'POST':
            jd_text = request.POST.get('jd_text', '').strip()
            uploaded_files = request.FILES.getlist('resume')

            if not jd_text:
                result_message = "Please provide a job description."
                result_image = static("images/error.png")  # Error image
                skills = [("Consider enhancing your resume with relevant skills.", static("images/Improve.png"))]
                return render(request, 'candidate_matching.html', {
                    'result_message': result_message,
                    'result_image': result_image,
                    'skills': skills,
                    'score': score,
                })

            if uploaded_files:
                try:
                    uploaded_file_paths = [extract_text_from_uploaded_pdf(file) for file in uploaded_files]
                    score = compare(uploaded_file_paths, jd_text, flag='HuggingFace-BERT')

                    my_dict = {uploaded_files[i].name: score[i] for i in range(len(score))}
                    sorted_dict = dict(sorted(my_dict.items()))
                    ct_items = list(sorted_dict.items())
                    score = ct_items[0][1]  # Get the score of the first file
                    sc = float(score)

                    if sc >= 75:
                        result_message = "The Candidate is a good match for the Job."
                        result_image = "https://media.istockphoto.com/id/1385218939/vector/people-crowd-applause-hands-clapping-business-teamwork-cheering-ovation-delight-vector.jpg?s=612x612&w=0&k=20&c=7NMaUB4zGoXoePxiy-XxKap53GMBQvmIYOSW1tVSFMY="
                    elif sc >= 50:
                        result_message = "The Candidate is a moderate match for the Job."
                        result_image = static("images/moderate.png")
                    else:
                        result_message = "The Candidate is not a good match for the Job."
                        result_image = static("images/bad.png")
                except Exception as e:
                    # Log the error and return a JSON response
                    logger.error(f"Error during file processing or comparison: {str(e)}")
                    return JsonResponse({'error': 'An error occurred while processing your files. Please try again.'}, status=500)

                try:
                    # Process Job Description and Extract skills
                    JD = preprocess_text(jd_text)
                    scored_df = calculate_scores(JD)
                    high_scores_df = scored_df[scored_df['Score'] >= 1]

                    if not high_scores_df.empty:
                        try:
                            data = pd.read_csv('csv/image.csv')  # Load CSV with skills and images

                            skills = []
                            for _, row in high_scores_df.iterrows():
                                skill_name = row['Domain/Area']

                                # Match skill with image from CSV
                                filtered_data = data[data['Skill'].str.lower().str.strip() == skill_name.lower().strip()]['Image'].values
                                img = filtered_data[0] if filtered_data.size > 0 else static("images/Improve.png")

                                skills.append((skill_name, img))
                        except Exception as e:
                            logger.error(f"Error loading CSV or processing skills: {str(e)}")
                            return JsonResponse({'error': 'An error occurred while processing skills. Please try again.'}, status=500)
                    else:
                        skills = [("Consider enhancing your resume with relevant skills.", static("images/Improve.png"))]
                except Exception as e:
                    logger.error(f"Error during JD processing or skill extraction: {str(e)}")
                    return JsonResponse({'error': 'An error occurred while processing the job description. Please try again.'}, status=500)

        return render(request, 'candidate_matching.html', {
            'result_message': result_message,
            'result_image': result_image,
            'skills': skills,
            'score': score,
        })

    except Exception as e:
        # Catch all unexpected errors and return a JSON response
        logger.error(f"Unexpected error in resume_screening: {str(e)}")
        return JsonResponse({'error': 'An unexpected error occurred. Please contact support.'}, status=500)


def interview_process(request):
    try:
        rollno = request.session.get('user_rollno')  # Get rollno from session
        
        if not rollno:
            messages.error(request, "You must be logged in to access the interview process details.")
            return redirect('stulogin')  # Redirect to login if no rollno in session

        # Read the company data from CSV
        company_names = []
        try:
            data = pd.read_csv('csv/company.csv', encoding='latin1')
            company_names = sorted(data['Company'].dropna().unique().tolist())  # Get sorted company names
        except Exception as e:
            logger.error(f"Error reading company CSV: {str(e)}")
            messages.error(request, "Unable to load company data. Please try again later.")

        # Get the selected company from the GET request
        company_name = request.GET.get('company_name', '').strip()

        info = ""
        rounds = {}
        images = []

        if company_name:
            try:
                company_info = data[data['Company'].str.strip() == company_name]

                if not company_info.empty:
                    company_info = company_info.iloc[0]
                    info = company_info.get('Info', 'No information available.')

                    # Collect round details in a dictionary format
                    rounds = {
                        f'Round {i}': company_info[f'Round {i}'] 
                        for i in range(1, 7) if pd.notna(company_info.get(f'Round {i}', None))
                    }

                    # Get images for the selected company (ensure function exists)
                    try:
                        images = search_and_display_images(company_name, 3)
                    except Exception as e:
                        logger.error(f"Error fetching images for {company_name}: {str(e)}")
                        messages.warning(request, f"Images for {company_name} could not be retrieved.")
                else:
                    messages.warning(request, f"No data found for {company_name}. Please check the selection.")
            except Exception as e:
                logger.error(f"Error processing company data for {company_name}: {str(e)}")
                messages.error(request, "Unable to fetch company details. Please try again later.")

        # Render the template with context data
        return render(request, 'interview_process.html', {
            'company_names': company_names,
            'info': info,
            'rounds': rounds,  # Dictionary of interview rounds
            'images': images,
            'company_name': company_name,
        })
    
    except Exception as e:
        logger.error(f"Unexpected error in interview process: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect('stulogin')


def search_and_display_images(query, num_images=3):
    try:
        images = []  
        url = f"https://www.google.com/search?q={query}&tbm=isch"  
        response = requests.get(url)  
        soup = BeautifulSoup(response.text, "html.parser")  
        
        for img in soup.find_all("img"):  
            if len(images) == num_images: 
                break
            src = img.get("src")  
            if src.startswith("http") and not src.endswith("gif"):  
                images.append(src)  

        return images
    except Exception as e:
        return []


def interview_preparation(request):
    try:
        rollno = request.session.get('user_rollno')  # Get rollno from session
        
        if not rollno:
            messages.error(request, "You must be logged in to access interview preparation resources.")
            return redirect('stulogin')  # Redirect to login if no rollno in session

        # Get selected level and category, default to "Easy"
        level = request.GET.get('level', 'Easy').strip()
        category = request.GET.get('category', '').strip()

        # Load the CSV file with questions and answers
        questions_list = []
        try:
            data = pd.read_csv('csv/Software Questions.csv', encoding='latin1')

            # Filter the questions based on the selected difficulty level
            filtered_questions = data[data['Difficulty'].str.strip() == level]

            # Get available categories for the selected level
            categories = sorted(set(filtered_questions['Category'].dropna().unique()))

            # If no category is selected, set it to the first available category for the selected level
            if not category and categories:
                category = categories[0]

            # If a category is selected but not in the available list, reset it
            if category and category not in categories:
                category = categories[0] if categories else ''

            # If a category is selected, filter questions by category
            if category:
                filtered_questions = filtered_questions[filtered_questions['Category'].str.strip() == category]

            # Convert questions to dictionary format
            questions_list = filtered_questions[['Question', 'Answer']].to_dict('records')

        except Exception as e:
            logger.error(f"Error reading questions CSV: {str(e)}")
            messages.error(request, "Unable to load question data. Please try again later.")
            categories = []  # Default to empty categories if error occurs

        # Load Video Links from Excel
        videos = []
        try:
            video_data = pd.read_excel('csv/VideoLinks.xlsx')

            # Ensure consistent formatting for filtering
            video_data['Level'] = video_data['Level'].astype(str).str.strip()
            video_data['Category'] = video_data['Category'].astype(str).str.strip()

            # Filter videos based on selected Level & Category
            filtered_videos = video_data[
                (video_data['Level'].str.lower() == level.lower()) &
                (video_data['Category'].str.lower() == category.lower())
            ]

            # Function to extract YouTube video ID
            def extract_video_id(url):
                patterns = [
                    r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
                    r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
                    r"youtu\.be/([a-zA-Z0-9_-]+)"
                ]
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        return match.group(1)
                return None

            # Prepare videos list
            for _, row in filtered_videos.iterrows():
                video_id = extract_video_id(row['Link'])
                if video_id:
                    videos.append({
                        "video_id": video_id,
                        "title": row.get('Title', f"{category} - {level}") 
                    })

        except Exception as e:
            logger.error(f"Error reading video links Excel: {str(e)}")
            messages.error(request, "Unable to load video data. Please try again later.")

        context = {
            'level': level,
            'category': category,
            'questions': questions_list,
            'videos': videos,
            'categories': categories,  # Only categories for the selected level
        }

        return render(request, 'interview_preparation.html', context)

    except Exception as e:
        logger.error(f"Unexpected error in interview preparation: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect('stulogin')  # Redirect to login page or an error page




#API_KEY = "AIzaSyDYEeSTrT7pPpVzpmaJ491gxogVxfWwpvM"

#API_KEY = "AIzaSyDukKA00FRAyVDyn0Q92IaftWPuC3BrvNs"

API_KEY = "AIzaSyApIE8uHcg1wcDZZNCPEY4qWSwxRifBQ8w"

def fetch_youtube_videos(query):
    """Fetch YouTube videos based on a search query."""
    youtube = build("youtube", "v3", developerKey=API_KEY)

    search_response = youtube.search().list(
        q=query,
        part="id,snippet",
        maxResults=18,
        type="video"
    ).execute()

    videos = []
    for item in search_response.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        thumbnail = item["snippet"]["thumbnails"]["default"]["url"]

        # Fetch comments and analyze sentiment
        positive_percentage = analyze_video_comments(video_id)

        if positive_percentage >= 50:  # Only include videos with 50% or more positive comments
            videos.append({
                "video_id": video_id,
                "title": title,
                "thumbnail": thumbnail,
                "positive_percentage": positive_percentage
            })
    return videos

def analyze_video_comments(video_id):
    """Fetch comments for a video, clean them, and perform sentiment analysis."""
    youtube = build("youtube", "v3", developerKey=API_KEY)

    comments = []
    try:
        video_response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100
        ).execute()

        for item in video_response.get("items", []):
            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            comments.append(clean_comment(comment))

    except Exception as e:
        print(f"Error fetching comments for video {video_id}: {e}")
        return 0  # If comments are unavailable, return 0% positivity

    # Perform sentiment analysis
    positive_comments = sum(1 for c in comments if get_sentiment(c) == "Positive")
    total_comments = len(comments)

    return (positive_comments / total_comments * 100) if total_comments > 0 else 0

def clean_comment(comment):
    """Remove URLs, punctuation, and emojis from a comment."""
    comment = re.sub(r"http\S+", "", comment)  # Remove links
    comment = emoji.demojize(comment)  # Remove emojis
    return comment

def get_sentiment(comment):
    """Classify the sentiment of a comment as Positive, Negative, or Neutral."""
    analysis = TextBlob(comment)
    if analysis.sentiment.polarity > 0:
        return "Positive"
    elif analysis.sentiment.polarity == 0:
        return "Neutral"
    else:
        return "Negative"

def course_recommendations(request):
    try:
        rollno = request.session.get('user_rollno')  # Get rollno from session
        
        if not rollno:
            messages.error(request, "You must be logged in to view course recommendations.")
            return redirect('stulogin')  # Redirect to login if no rollno in session

        query = ""
        videos = []

        if request.method == "GET" and "query" in request.GET:
            query = request.GET["query"] + " course"
            try:
                # Assuming fetch_youtube_videos is a function that fetches video results
                videos = fetch_youtube_videos(query)
            except Exception as e:
                logger.error(f"Error fetching YouTube videos for query '{query}': {str(e)}")
                messages.error(request, "Unable to fetch video data. Please try again later.")

        context = {
            "videos": videos,
            "query": query
        }
        return render(request, "course_recommendations.html", context)

    except Exception as e:
        logger.error(f"Unexpected error in course_recommendations: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect('stulogin')

def notifications(request):
    try:
        rollno = request.session.get('user_rollno')  # Get roll number from session

        if not rollno:
            messages.error(request, "You must be logged in to view notifications.")
            return redirect('stulogin')  # Redirect to login if no roll number in session

        try:
            student = StudentRegistration.objects.get(rollno=rollno)  # Get student instance
        except ObjectDoesNotExist:
            messages.error(request, "Student not found. Please contact support.")
            return redirect('stulogin')  # Redirect to login if student not found

        # Fetch notifications for the student
        notifications = Notification.objects.filter(student=student).order_by('-timestamp')

        for notification in notifications:
            try:
                # Try to fetch eligibility for each notification
                eligibility = Eligibility.objects.filter(student=student, company=notification.company).first()

                if eligibility:
                    logger.info(f"✅ Eligibility found for {student.rollno} - {notification.company.name}: {eligibility.application_status}")
                else:
                    logger.warning(f"❌ Eligibility NOT found for {student.rollno} - {notification.company.name}")

                notification.eligibility = eligibility  # Attach eligibility to notification

            except Exception as e:
                logger.error(f"Error fetching eligibility for student {student.rollno} and company {notification.company.name}: {str(e)}")
                notification.eligibility = 'NOT_ELIGIBLE'  # Set eligibility in case of error

        # Mark all notifications as seen, ensuring errors don't interrupt this process
        try:
            notifications.update(seen=True)
        except Exception as e:
            logger.error(f"Error marking notifications as seen for student {student.rollno}: {str(e)}")

        return render(request, 'notifications.html', {'notifications': notifications})

    except Exception as e:
        logger.error(f"Unexpected error in notifications view: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect('stulogin')
    

"""def applied_jobs(request):
    rollno = request.session.get("user_rollno")  # Get roll number from session

    if not rollno:
        return redirect("stulogin")  # Redirect to login page if not logged in

    student = StudentRegistration.objects.get(rollno=rollno)  # Get student (assuming always exists)
    
    # Fetch all eligibility records where original status is "ELIGIBLE_APPLIED"
    applied_jobs = Eligibility.objects.filter(student=student, original_status="ELIGIBLE_APPLIED")

    for job in applied_jobs:
        # Get the most recent notification related to this student and company
        latest_notification = Notification.objects.filter(student=student, company=job.company).order_by('-timestamp').first()
        
        # Set the latest notification message if available, otherwise default to "No notifications yet."
        job.latest_notification = latest_notification.message if latest_notification else "No notifications yet."
        
        # Update the Eligibility status based on the latest notification (if needed)
        if latest_notification:
            # Normalize message to lower case and check for specific terms
            message_lower = latest_notification.message.lower()

            # Check if the current status is not REJECTED before processing any other status updates
            if job.application_status != "REJECTED":
                if "qualified" in message_lower:
                    job.application_status = "PROCESSING"  # Status changes to PROCESSING when qualified
                elif "selected" in message_lower:
                    job.application_status = "PLACED"  # Status changes to PLACED when selected
                elif "not qualified" in message_lower or "rejected" in message_lower:
                    job.application_status = "REJECTED"  # Status changes to REJECTED when not qualified or rejected
                else:
                    job.application_status = "ELIGIBLE_APPLIED"  # Default status if no specific match
                job.save()  # Save the updated application status

    return render(request, "applied_jobs.html", {"applied_jobs": applied_jobs})"""

def upload_offer_letter(request):
    try:
        rollno = request.session.get('user_rollno')

        if not rollno:
            messages.error(request, "Student not logged in.")
            return redirect('upload_offer_letter')

        # Get StudentProfile instead of StudentRegistration
        try:
            student_profile = StudentProfile.objects.get(student__rollno=rollno)
        except StudentProfile.DoesNotExist:
            messages.error(request, "Student profile not found. Please complete your profile first.")
            return redirect('upload_offer_letter')

        companies = Company.objects.all()  # Fetch all companies

        if request.method == 'POST':
            form = PlacementOfferForm(request.POST, request.FILES)
            if form.is_valid():
                company = form.cleaned_data['company']  # Get selected company
                offer_letters = request.FILES.getlist('offer_letter')  # Get all files

                if not offer_letters:
                    messages.error(request, "Please select a file to upload.")
                    return redirect('upload_offer_letter')

                for offer_letter in offer_letters:
                    # Validate file type (only allow PDFs)
                    if not offer_letter.name.endswith('.pdf'):
                        messages.error(request, "Only PDF files are allowed.")
                        return redirect('upload_offer_letter')

                    # Validate file size (limit: 2MB)
                    if offer_letter.size > 2 * 1024 * 1024:
                        messages.error(request, "Offer letter file size exceeds the limit of 2MB.")
                        return redirect('upload_offer_letter')

                    try:
                        # Check if an offer already exists for this student & company
                        existing_offer = PlacementOffer.objects.filter(student=student_profile, company=company).first()

                        if existing_offer:
                            existing_offer.offer_letter = offer_letter  # Update existing offer letter
                            existing_offer.save()
                            messages.success(request, f"Offer letter updated for {company.name}.")
                        else:
                            placement_offer = PlacementOffer(student=student_profile, company=company, offer_letter=offer_letter)
                            placement_offer.save()
                            messages.success(request, f"Offer letter uploaded successfully for {company.name}!")

                    except Exception as e:
                        logger.error(f"Error saving placement offer for student {student_profile.student.rollno}, company {company.name}: {str(e)}")
                        messages.error(request, "Error saving the offer letter. Please try again.")
                        return redirect('upload_offer_letter')

                return redirect('upload_offer_letter')

            else:
                messages.error(request, "Invalid form submission. Please check your inputs.")

        else:
            form = PlacementOfferForm()

        return render(request, 'upload_offer_letter.html', {
            'form': form,
            'companies': companies,  # Pass the companies to the template
        })

    except Exception as e:
        logger.error(f"Unexpected error in upload_offer_letter view: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect('upload_offer_letter')
    
    
def applied_jobs(request):
    try:
        rollno = request.session.get("user_rollno")  # Get roll number from session

        if not rollno:
            messages.error(request, "You must be logged in to view applied jobs.")
            return redirect("stulogin")  # Redirect to login page if not logged in

        try:
            student = StudentRegistration.objects.get(rollno=rollno)  # Get student
        except ObjectDoesNotExist:
            messages.error(request, "Student record not found. Please contact support.")
            return redirect("stulogin")  # Redirect to login page if student not found

        # Fetch all eligibility records where original status is "ELIGIBLE_APPLIED"
        applied_jobs = Eligibility.objects.filter(student=student, original_status="ELIGIBLE_APPLIED")

        for job in applied_jobs:
            # Default message for job notification
            job.latest_notification = "No notifications yet."
            
            # Get application status
            application_status = job.application_status

            if application_status == "PROCESSING":
                try:
                    latest_notification = Notification.objects.filter(
                        student=student,
                        company=job.company
                    ).order_by('-timestamp').first()
                    
                    if latest_notification:
                        job.latest_notification = latest_notification.message
                    else:
                        job.latest_notification = "Your application is in processing. No updates yet."

                except Exception as e:
                    logger.error(f"Error fetching notification for {student.rollno}: {str(e)}")
                    job.latest_notification = "Error retrieving notifications."

            elif application_status == "PLACED":
                job.latest_notification = "Congratulations! You have been placed."
            elif application_status == "REJECTED":
                job.latest_notification = "Unfortunately, your application was rejected."

            # Save changes if necessary
            try:
                job.save()
            except Exception as e:
                logger.error(f"Error saving job status for student {student.rollno}: {str(e)}")

        return render(request, "applied_jobs.html", {"applied_jobs": applied_jobs})

    except Exception as e:
        logger.error(f"Unexpected error in applied_jobs view: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please contact support.")
        return redirect("stulogin")  