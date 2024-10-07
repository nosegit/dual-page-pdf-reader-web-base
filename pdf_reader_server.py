import os
import math
import shutil
import multiprocessing
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from signal import signal, SIGPIPE, SIG_DFL  
signal(SIGPIPE,SIG_DFL) 

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

poppler_bin_path = ""
if os.name == "nt":
    print("Running on Windows")
    # Path to the Poppler bin folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    poppler_bin_path = os.path.join(script_dir, 'poppler-24.07.0', 'Library', 'bin')
elif os.name == "posix":
    poppler_bin_path = "/usr/bin"
    print("Running on Linux or another POSIX OS")


progress_value = 0  # Global variable to track progress



class PDFReader:
    def __init__(self, poppler_bin_path):
        self.pages = []
        self.poppler_bin_path = poppler_bin_path
        self.progress = {'value': 0}  # Initialize progress tracking
        self.batch_size = 40

    def convert_to_image_files(self, file_path, batch_size):
        global progress_value  # Use global variable
        self.batch_size = batch_size

        with open(file_path, 'rb') as pdf_file:
            pdf_reader = PdfReader(pdf_file)
            
            file_name = os.path.basename(file_path).split(".pdf")[0]
            directory_name = os.path.dirname(file_path)

            # Iterate over all pages and save each batch pages as a separate PDF
            for index, page_number in enumerate(range(0, len(pdf_reader.pages), batch_size)):
                pdf_writer = PdfWriter()

                for page_num in range(page_number,min(page_number+batch_size+1,len(pdf_reader.pages))):
                    pdf_writer.add_page(pdf_reader.pages[page_num])
                
                output_pdf_path = os.path.join(directory_name, f"{ file_name }_{ index }.pdf" )
                
                # Write the page to a new PDF file
                with open(output_pdf_path, 'wb') as output_pdf:
                    pdf_writer.write(output_pdf)
                
                print(f"Saved page {page_number}:{min(page_number+batch_size+1,len(pdf_reader.pages)+1)} to {output_pdf_path}")

                self.pages = []
                self.convert_pdf_to_images(output_pdf_path)
                self.shrink_pages_to_smallest()
                self.save_images_concurrently(self.pages,app.config['IMAGE_FOLDER'],page_number)
                progress_value = (index+1) / math.ceil(len(pdf_reader.pages)/batch_size ) *100


    def convert_pdf_to_images(self, file_path):

        # Get total number of pages using PyPDF2
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)

        with multiprocessing.Manager() as manager:
            completed_count = manager.Value('i', 0)  # Shared variable to track completed tasks

            # Convert pages using multiprocessing
            with multiprocessing.Pool() as pool:
                # Prepare the arguments for each batch
                for batch_start in range(1, total_pages + 1, self.batch_size):
                    batch_end = min(batch_start + self.batch_size - 1, total_pages)
                    args = [(file_path, i, self.poppler_bin_path, completed_count, total_pages) for i in range(batch_start, batch_end + 1)]

                    # Process the batch
                    batch_results = pool.starmap(self.convert_single_page, args)

                    # Append results to pages
                    for page in batch_results:
                        if page is not None:
                            self.pages.append(page)

                    print(f"Conversion started!!")

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

        # Find the smallest page size
        if not self.pages:
            return  # No pages to process

        smallest_width = min(page.size[0] for page in self.pages)
        smallest_height = min(page.size[1] for page in self.pages)

        with multiprocessing.Manager() as manager:
            completed_count = manager.Value('i', 0)  # Shared variable to track completed tasks

            # Resize all pages using multiprocessing
            with multiprocessing.Pool() as pool:
                for i in range(0, len(self.pages), self.batch_size):
                    batch = self.pages[i:i + self.batch_size]
                    args = [(page, smallest_width, smallest_height, completed_count, len(batch)) for page in batch]

                    # Process the batch
                    resized_batch = pool.starmap(self.resize_page, args)

                    # Append resized pages to pages list
                    self.pages[i:i + len(resized_batch)] = resized_batch

                    print(f"Resizing Started!")  # Debug print statement


    @staticmethod
    def resize_page(page, width, height, completed_count, total_pages):
        resized_page = page.resize((width, height), Image.LANCZOS)
        return resized_page

    def save_images_concurrently(self, pages, image_folder , page_offset):

        #Function to save images concurrently using multiprocessing.
        total_pages = len(pages)
        pool_args = [(page, os.path.join(image_folder, f"page_{i+ page_offset + 1}.png")) for i, page in enumerate(pages)]

        # Create a multiprocessing Pool to save images concurrently
        with multiprocessing.Pool() as pool:
            for i, success in enumerate(pool.imap_unordered(self.save_image, pool_args)):
                print(f"Saving images: {page_offset + i + 1}")
    
    @staticmethod      
    def save_image(args):
        #Function to save a single image.
        page, image_path = args
        try:
            page.save(image_path, 'PNG')
            return True
        except Exception as e:
            print(f"Error saving image to {image_path}: {e}")
            return False

@app.route('/')
def index():
    global progress_value
    progress_value = 0
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
        pdf_reader.convert_to_image_files(pdf_path,40)

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
