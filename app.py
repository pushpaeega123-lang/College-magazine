import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import gridfs
import os
import uuid
from functools import wraps
from dotenv import load_dotenv
from io import BytesIO

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB max file size

# MongoDB configuration
mongo_uri = os.getenv('MONGO_URI', 'mongodb+srv://gnana:gnana123@newcluster.hirw8ro.mongodb.net/college_magazine?retryWrites=true&w=majority&appName=Newcluster')
client = MongoClient(mongo_uri)
db = client.get_database('college_magazine')  # Explicitly specify the database name
fs = gridfs.GridFS(db)

# Collections
students_collection = db['students']
events_collection = db['events']
news_collection = db['news']
gallery_collection = db['gallery']
registrations_collection = db['registrations']

# Admin credentials (in production, use environment variables or a more secure method)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

def save_file(file, collection_name):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_id = fs.put(
            file,
            filename=filename,
            content_type=file.content_type,
            metadata={"collection": collection_name}
        )
        return str(file_id)
    return None

def get_file(file_id):
    try:
        file_data = fs.get(ObjectId(file_id))
        return file_data
    except:
        return None

def delete_file(file_id):
    try:
        fs.delete(ObjectId(file_id))
        return True
    except:
        return False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please login as admin to access this page.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('student_id'):
            flash('Please login to access this page.', 'error')
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get counts for dashboard
    news_count = news_collection.count_documents({})
    events_count = events_collection.count_documents({})
    gallery_count = gallery_collection.count_documents({})
    students_count = students_collection.count_documents({})
    
    return render_template('admin_dashboard.html', 
                         news_count=news_count,
                         events_count=events_count,
                         gallery_count=gallery_count,
                         students_count=students_count)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

# News Management
@app.route('/admin/news')
@admin_required
def admin_news():
    # Convert cursor to list and add string version of _id for templates
    news_list = list(news_collection.find().sort('date_posted', -1))
    for item in news_list:
        item['_id'] = str(item['_id'])
        if 'date_posted' in item and isinstance(item['date_posted'], datetime):
            item['date_posted_str'] = item['date_posted'].strftime('%B %d, %Y')
    return render_template('admin_news.html', news=news_list)

@app.route('/admin/news/add', methods=['GET', 'POST'])
@admin_required
def admin_add_news():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files['image']
        
        # Save the file to GridFS
        file_id = save_file(file, 'news') if file else None
        
        news_data = {
            'title': title,
            'content': content,
            'date_posted': datetime.utcnow(),
            'image_id': file_id
        }
        
        news_collection.insert_one(news_data)
        flash('News added successfully!', 'success')
        return redirect(url_for('admin_news'))
    
    return render_template('admin_add_news.html')

@app.route('/admin/news/edit/<news_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_news(news_id):
    news = news_collection.find_one({'_id': ObjectId(news_id)})
    if not news:
        flash('News not found!', 'error')
        return redirect(url_for('admin_news'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files['image']
        
        update_data = {
            'title': title,
            'content': content,
            'date_posted': news['date_posted']
        }
        
        if file and allowed_file(file.filename):
            # Delete existing file
            if news.get('image_id'):
                delete_file(news['image_id'])
            
            # Save the new file to GridFS
            file_id = save_file(file, 'news')
            update_data['image_id'] = file_id
        else:
            update_data['image_id'] = news.get('image_id')
        
        news_collection.update_one({'_id': ObjectId(news_id)}, {'$set': update_data})
        flash('News updated successfully!', 'success')
        return redirect(url_for('admin_news'))
    
    return render_template('admin_edit_news.html', news=news)

@app.route('/admin/news/delete/<news_id>')
@admin_required
def admin_delete_news(news_id):
    news = news_collection.find_one({'_id': ObjectId(news_id)})
    if news.get('image_id'):
        delete_file(news['image_id'])
    
    news_collection.delete_one({'_id': ObjectId(news_id)})
    flash('News deleted successfully!', 'success')
    return redirect(url_for('admin_news'))

@app.route('/news/image/<file_id>')
def news_image(file_id):
    file_data = get_file(file_id)
    if file_data:
        return send_file(
            BytesIO(file_data.read()),
            mimetype=file_data.content_type,
            download_name=file_data.filename
        )
    return "Image not found", 404

# Events Management
@app.route('/admin/events')
@admin_required
def admin_events():
    # Convert cursor to list and add string version of _id for templates
    events = list(events_collection.find().sort('created_at', -1))
    for event in events:
        event['_id'] = str(event['_id'])
        if 'date' in event and isinstance(event['date'], datetime):
            event['date_str'] = event['date'].strftime('%B %d, %Y')
    return render_template('admin_events.html', events=events)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@admin_required
def admin_add_event():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        location = request.form['location']
        file = request.files['image']
        
        # Save the file to GridFS
        file_id = save_file(file, 'events') if file else None
        
        event_data = {
            'title': title,
            'description': description,
            'date': datetime.strptime(date, '%Y-%m-%d'),
            'location': location,
            'created_at': datetime.utcnow(),
            'image_id': file_id
        }
        
        events_collection.insert_one(event_data)
        flash('Event added successfully!', 'success')
        return redirect(url_for('admin_events'))
    
    return render_template('admin_add_event.html')

@app.route('/admin/events/edit/<event_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_event(event_id):
    event = events_collection.find_one({'_id': ObjectId(event_id)})
    if not event:
        flash('Event not found!', 'error')
        return redirect(url_for('admin_events'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        location = request.form['location']
        file = request.files['image']
        
        update_data = {
            'title': title,
            'description': description,
            'date': datetime.strptime(date, '%Y-%m-%d'),
            'location': location,
            'created_at': event['created_at']
        }
        
        if file and allowed_file(file.filename):
            # Delete existing file
            if event.get('image_id'):
                delete_file(event['image_id'])
            
            # Save the new file to GridFS
            file_id = save_file(file, 'events')
            update_data['image_id'] = file_id
        else:
            update_data['image_id'] = event.get('image_id')
        
        events_collection.update_one({'_id': ObjectId(event_id)}, {'$set': update_data})
        flash('Event updated successfully!', 'success')
        return redirect(url_for('admin_events'))
    
    return render_template('admin_edit_event.html', event=event)

@app.route('/admin/events/delete/<event_id>')
@admin_required
def admin_delete_event(event_id):
    event = events_collection.find_one({'_id': ObjectId(event_id)})
    if event.get('image_id'):
        delete_file(event['image_id'])
    
    events_collection.delete_one({'_id': ObjectId(event_id)})
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('admin_events'))

@app.route('/events/image/<file_id>')
def events_image(file_id):
    file_data = get_file(file_id)
    if file_data:
        return send_file(
            BytesIO(file_data.read()),
            mimetype=file_data.content_type,
            download_name=file_data.filename
        )
    return "Image not found", 404

@app.route('/admin/events/registrations/<event_id>')
@admin_required
def admin_event_registrations(event_id):
    # Get the event
    event = events_collection.find_one({'_id': ObjectId(event_id)})
    if not event:
        flash('Event not found!', 'error')
        return redirect(url_for('admin_events'))
    
    # Get all registrations for this event
    registrations = list(registrations_collection.find({'event_id': event_id}))
    
    # Get student details for each registration
    registered_students = []
    for reg in registrations:
        student = students_collection.find_one({'_id': ObjectId(reg['student_id'])})
        if student:
            registered_students.append({
                'name': student.get('name', 'N/A'),
                'email': student.get('email', 'N/A'),
                'roll_no': student.get('roll_no', 'N/A'),
                'registered_at': reg.get('registered_at', datetime.utcnow()).strftime('%B %d, %Y %H:%M')
            })
    
    return render_template('admin_event_registrations.html', 
                         event=event,
                         registrations=registered_students)

# Gallery Management
@app.route('/admin/gallery')
@admin_required
def admin_gallery():
    # Convert cursor to list and add string version of _id for templates
    images = list(gallery_collection.find().sort('date', -1))
    for img in images:
        img['_id'] = str(img['_id'])
        if 'date' in img and isinstance(img['date'], datetime):
            img['date_str'] = img['date'].strftime('%B %d, %Y')
    return render_template('admin_gallery.html', images=images)

@app.route('/admin/gallery/add', methods=['GET', 'POST'])
@admin_required
def admin_add_image():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['image']
        
        # Save the file to GridFS
        file_id = save_file(file, 'gallery') if file else None
        
        image_data = {
            'title': title,
            'description': description,
            'date': datetime.utcnow(),
            'image_id': file_id
        }
        
        gallery_collection.insert_one(image_data)
        flash('Image added successfully!', 'success')
        return redirect(url_for('admin_gallery'))
    
    return render_template('admin_add_image.html')

@app.route('/admin/gallery/delete/<image_id>')
@admin_required
def admin_delete_image(image_id):
    image = gallery_collection.find_one({'_id': ObjectId(image_id)})
    if image.get('image_id'):
        delete_file(image['image_id'])
    
    gallery_collection.delete_one({'_id': ObjectId(image_id)})
    flash('Image deleted successfully!', 'success')
    return redirect(url_for('admin_gallery'))

@app.route('/gallery/image/<file_id>')
def gallery_image(file_id):
    file_data = get_file(file_id)
    if file_data:
        return send_file(
            BytesIO(file_data.read()),
            mimetype=file_data.content_type,
            download_name=file_data.filename
        )
    return "Image not found", 404

# Student Routes
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    import re
    if request.method == 'POST':
        roll_no = request.form['roll_no']
        email = request.form['email']
        name = request.form['name']
        password = request.form['password']

        # Roll number format validation (e.g., 23F01A0540)
        roll_pattern = r'^\d{2}[A-Z]\d{2}[A-Z]\d{4}$'
        if not re.match(roll_pattern, roll_no):
            flash('Invalid roll number format! Format should be like 23F01A0540.', 'error')
            return render_template('student_register.html')

        # Check if student already exists
        if students_collection.find_one({'roll_no': roll_no}):
            flash('Student with this roll number already exists!', 'error')
            return render_template('student_register.html')

        if students_collection.find_one({'email': email}):
            flash('Student with this email already exists!', 'error')
            return render_template('student_register.html')

        student_data = {
            'roll_no': roll_no,
            'email': email,
            'name': name,
            'password': generate_password_hash(password),
            'created_at': datetime.utcnow()
        }

        students_collection.insert_one(student_data)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('student_login'))

    return render_template('student_register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        roll_no = request.form['roll_no']
        password = request.form['password']
        
        student = students_collection.find_one({'roll_no': roll_no})
        
        if student and check_password_hash(student['password'], password):
            session['student_id'] = str(student['_id'])
            session['student_name'] = student['name']
            flash('Login successful!', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('student_login.html')

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    # Get recent data for dashboard
    recent_news = list(news_collection.find().sort('date_posted', -1).limit(3))
    upcoming_events = list(events_collection.find({'date': {'$gte': datetime.utcnow()}}).sort('date', 1).limit(3))
    recent_images = list(gallery_collection.find().sort('date', -1).limit(6))
    
    return render_template('student_dashboard.html', 
                         recent_news=recent_news,
                         upcoming_events=upcoming_events,
                         recent_images=recent_images)

@app.route('/student/logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/student/my-events')
@student_required
def student_my_events():
    student_id = session.get('student_id')
    
    # Get all registrations for this student
    registrations = list(registrations_collection.find({'student_id': student_id}))
    
    # Get event details for each registration
    registered_events = []
    for reg in registrations:
        event = events_collection.find_one({'_id': ObjectId(reg['event_id'])})
        if event:
            event['registered_at'] = reg['registered_at']
            registered_events.append(event)
    
    return render_template('student_my_events.html', events=registered_events)

# Public Pages
@app.route('/news')
def news():
    news_list = list(news_collection.find().sort('date_posted', -1))
    return render_template('news.html', news=news_list)

@app.route('/events')
def events():
    events_list = list(events_collection.find().sort('date', -1))
    return render_template('events.html', events=events_list)

@app.route('/gallery')
def gallery():
    images = list(gallery_collection.find().sort('date', -1))
    return render_template('gallery.html', images=images)

@app.route('/events/register/<event_id>', methods=['POST'])
@student_required
def register_for_event(event_id):
    try:
        # Check if the event exists
        event = events_collection.find_one({'_id': ObjectId(event_id)})
        if not event:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        # Check if student is already registered
        existing_registration = registrations_collection.find_one({
            'event_id': event_id,
            'student_id': session['student_id']
        })
        
        if existing_registration:
            return jsonify({'success': False, 'message': 'You are already registered for this event'}), 400
        
        # Register the student for the event
        registration = {
            'event_id': event_id,
            'student_id': session['student_id'],
            'registered_at': datetime.utcnow()
        }
        
        registrations_collection.insert_one(registration)
        return jsonify({
            'success': True, 
            'message': 'Successfully registered for the event!'
        })
        
    except Exception as e:
        print(f"Error registering for event: {str(e)}")
        return jsonify({
            'success': False, 
            'message': 'An error occurred while processing your registration.'
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')