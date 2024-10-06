import os
import shutil
import multiprocessing
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfReader

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

# Define folder to store uploaded PDFs and converted images
UPLOAD_FOLDER = 'uploads'
IMAGE_FOLDER = 'static/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['IMAGE_FOLDER'] = IMAGE_FOLDER

# Ensure upload and image folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

# Path to the Poppler bin folder
script_dir = os.path.dirname(os.path.abspath(__file__))
poppler_bin_path = os.path.join(script_dir, 'poppler-24.07.0', 'Library', 'bin')

progress_value = 0  # Global variable to track progress



class PDFReader:
    def __init__(self, poppler_bin_path):
        self.pages = []
        self.poppler_bin_path = poppler_bin_path
        self.progress = {'value': 0}  # Initialize progress tracking

    def convert_pdf_to_images(self, file_path):
        global progress_value  # Use global variable

        # Get total number of pages using PyPDF2
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)

        batch_size = 40  # Define your batch size
        with multiprocessing.Manager() as manager:
            completed_count = manager.Value('i', 0)  # Shared variable to track completed tasks

            # Convert pages using multiprocessing
            with multiprocessing.Pool() as pool:
                # Prepare the arguments for each batch
                for batch_start in range(1, total_pages + 1, batch_size):
                    batch_end = min(batch_start + batch_size - 1, total_pages)
                    args = [(file_path, i, self.poppler_bin_path, completed_count, total_pages) for i in range(batch_start, batch_end + 1)]

                    # Process the batch
                    batch_results = pool.starmap(self.convert_single_page, args)

                    # Append results to pages
                    for page in batch_results:
                        if page is not None:
                            self.pages.append(page)

                    # Update progress bar for conversion (0-33%)
                    completed_count.value += len(args)
                    progress_value = (completed_count.value / total_pages) * 33
                    print(f"Conversion Progress: {progress_value}%")  # Debug print statement

        return self.pages

    @staticmethod
    def convert_single_page(file_path, page_number, poppler_bin_path, completed_count, total_pages):
        # Convert a single page from PDF to image
        try:
            page = convert_from_path(file_path, first_page=page_number, last_page=page_number, poppler_path=poppler_bin_path)[0]
            return page
        except Exception as e:
            print(f"Error converting page {page_number}: {e}")
            return None

    def shrink_pages_to_smallest(self):
        global progress_value  # Use global variable

        # Find the smallest page size
        if not self.pages:
            return  # No pages to process

        smallest_width = min(page.size[0] for page in self.pages)
        smallest_height = min(page.size[1] for page in self.pages)

        batch_size = 50  # Define your batch size
        with multiprocessing.Manager() as manager:
            completed_count = manager.Value('i', 0)  # Shared variable to track completed tasks

            # Resize all pages using multiprocessing
            with multiprocessing.Pool() as pool:
                for i in range(0, len(self.pages), batch_size):
                    batch = self.pages[i:i + batch_size]
                    args = [(page, smallest_width, smallest_height, completed_count, len(batch)) for page in batch]

                    # Process the batch
                    resized_batch = pool.starmap(self.resize_page, args)

                    # Append resized pages to pages list
                    self.pages[i:i + len(resized_batch)] = resized_batch

                    # Update progress bar for resizing (50-100%)
                    completed_count.value += len(args)
                    progress_value = 33 + (completed_count.value / len(self.pages)) * 33
                    print(f"Resizing Progress: {progress_value}%")  # Debug print statement

    @staticmethod
    def resize_page(page, width, height, completed_count, total_pages):
        resized_page = page.resize((width, height), Image.LANCZOS)
        return resized_page


@app.route('/')
def index():
    session['progress'] = 0
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global progress_value  # Use global variable

    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)

        # Clean the IMAGE_FOLDER before saving new images
        if os.path.exists(app.config['IMAGE_FOLDER']):
            shutil.rmtree(app.config['IMAGE_FOLDER'])
        os.makedirs(app.config['IMAGE_FOLDER'])


        # Convert the PDF to images
        pdf_reader = PDFReader(poppler_bin_path)
        pdf_reader.convert_pdf_to_images(pdf_path)

        # Resize images to the smallest dimensions
        pdf_reader.shrink_pages_to_smallest()

        total_pages = len(pdf_reader.pages)
        for i, page in enumerate(pdf_reader.pages):
            if page:
                image_path = os.path.join(app.config['IMAGE_FOLDER'], f"page_{i + 1}.png")
                page.save(image_path, 'PNG')
            progress_value = 66 + (i/total_pages) * 34

        # Redirect to dual-page view with the number of pages
        return redirect(url_for('viewer', page1=0, page2=1))
    
    return 'Only PDF files are allowed.'

@app.route('/viewer')
def viewer():
    page1 = request.args.get('page1', default=0, type=int)
    page2 = request.args.get('page2', default=1, type=int)

    total_pages = len(os.listdir(app.config['IMAGE_FOLDER']))
    
    return render_template('viewer.html', page1=page1, page2=page2, total_pages=total_pages)

@app.route('/images/<filename>')
def images(filename):
    return send_from_directory(app.config['IMAGE_FOLDER'], filename)

@app.route('/progress')
def progress():
    global progress_value  # Use global variable

    # Return the current progress value
    return {'progress': progress_value}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
