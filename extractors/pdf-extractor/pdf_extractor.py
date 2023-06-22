import logging
import os
import shutil
import subprocess
import tempfile

from pyclowder.extractors import Extractor
from pyclowder.files import upload_preview
from pyclowder.files import upload_metadata
from pypdf import PdfReader, PdfWriter
from pathvalidate import sanitize_filename

MAX_PDF_MB = 10 

class PDFExtractor(Extractor):
    def __init__(self):
        Extractor.__init__(self)
        logging.getLogger('pyclowder').setLevel(logging.DEBUG)
        logging.getLogger('__main__').setLevel(logging.DEBUG)

        self.setup()

    def process_message(self, connector, host, secret_key, resource, parameters):
        logger = logging.getLogger(__name__)
        file_path = resource["local_paths"][0]
        file_id = resource['id']
        file_name = sanitize_filename(resource['name'])
        # ensure it ends in .pdf
        if not file_name.lower().endswith('.pdf'):
            file_name += '.pdf'

        logger.debug(resource)

        # Process the PDF file
        with open(file_path, 'rb') as pdf_file:
            reader = PdfReader(pdf_file)

            tempdir=tempfile.mkdtemp()
            preview_path = os.path.join(tempdir, file_name)
            
            file_stats = os.stat(file_path)
            file_mb = file_stats.st_size / (1024 * 1024)
            copy_failed = False
            if file_mb < MAX_PDF_MB:
                # Make a copy of the file as  preview
                logger.debug("PDF size is %8.2f MB, making a plain copy" % file_mb)
                shutil.copyfile(file_path, preview_path)
            else:
                # Do a lossless compression with Ghostscript
                logger.debug("PDF size is %8.2f MB, attempting compression" % file_mb)
                try:
                    subprocess.check_call(['gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dNOPAUSE', '-dQUIET', '-dBATCH', '-sOutputFile=%s' % preview_path, file_path])
                    # If file is still too big, be more aggressive
                    file_stats = os.stat(preview_path)
                    file_mb = file_stats.st_size / (1024 * 1024)
                    if file_mb > MAX_PDF_MB:
                        logger.debug("PDF size is still %8.2f MB, attempting lossy compression" % file_mb)
                        try:
                            subprocess.check_call(['gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dQUIET', '-dBATCH', '-sOutputFile=%s' % preview_path, file_path])
                        except subprocess.CalledProcessError as e:
                            logging.getLogger().exception("Lossy ghostscript compression of " + inputfile)
                            copy_failed = True
                except subprocess.CalledProcessError as e:
                    logging.getLogger().exception("ghostscript compression of " + inputfile)
                    copy_failed = True

            # If we failed to do ghostscript compression, just make a copy
            if copy_failed:
                logger.debug("Ghostscript compression of PDF failed, making a plain copy")
                shutil.copyfile(file_path, preview_path)

            # Upload the preview
            preview_id = upload_preview(connector, host, secret_key, file_id, preview_path, None)

            # Also create and upload a preview image
            # gs -dNOPAUSE -q -sDEVICE=png256 -r500 -dBATCH -dFirstPage=1 -dLastPage=1 -sOutputFile=out.png in.pdf
            preview_image_ids=[]
            try:
                png_preview_path = os.path.join(tempdir, 'temp.png')
                for page in range(len(reader.pages)):
                    page_num = page+1
                    webp_preview_path = os.path.join(tempdir, 'page_%03d.webp' % page_num)
                    subprocess.check_call(['gs', '-sDEVICE=png256', '-r500', '-dFirstPage=%d'% page_num, '-dLastPage=%d' % page_num, '-dNOPAUSE', '-dQUIET', '-dBATCH', '-sOutputFile=%s' % png_preview_path, file_path])
                    subprocess.check_call(['convert', '-resize', '512X', png_preview_path, png_preview_path])
                    subprocess.check_call(['cwebp', '-quiet', png_preview_path, '-o', webp_preview_path])
                    # Upload the webp preview
                    preview_image_ids.append(upload_preview(connector, host, secret_key, file_id, webp_preview_path, None))
            except subprocess.CalledProcessError as e:
                logging.getLogger().exception("Create of preview image failed!")
            

            # Check whether landscape
            # identify -format '%w %h' test.png | awk '{if ($1<$2) {exit 1} else {exit 0} }'

            # Create and save metadata as well
            result = {
                'preview_pdf': preview_id,
                'num_pages': len(reader.pages),
                'preview_images': preview_image_ids,
                'size_mb': os.stat(preview_path).st_size / (1024 * 1024)
            }
            metadata = self.get_metadata(result, 'file', file_id, host)
            upload_metadata(connector, host, secret_key, file_id, metadata)  
            
            # Perform additional PDF processing
            # Add your code here to extract text, images, or perform other operations on the PDF

            # Example: Notify success
            logger.debug("PDF extraction complete (previews: PDF %8.2f MB, Image %8.2f KB)!" % (result['size_mb'], os.stat(webp_preview_path).st_size / 1024))


if __name__ == "__main__":
    extractor = PDFExtractor()
    extractor.start()
